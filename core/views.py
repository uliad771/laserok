import json
import uuid
from collections import Counter
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Count, F, Q, DecimalField
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from .models import Product, Shift, Sale, SaleItem, StockMovement, OnlineOrder


def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="Администраторы").exists()
    )


def ctx(user):
    return {"is_admin": is_admin(user)}


def home(request):
    return redirect("pos" if request.user.is_authenticated else "login")


@login_required
def pos(request):
    return render(request, "core/pos.html", ctx(request.user))


@login_required
def api_products(request):
    q = request.GET.get("q", "").strip()
    products = Product.objects.filter(is_active=True)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode=q))
    return JsonResponse({"products": [{
        "id": p.pk, "name": p.name, "sku": p.sku, "price": str(p.price),
        "stock": p.stock, "min_stock": p.min_stock,
        "emoji": getattr(p, "emoji", "📦"),
        "image": p.image.url if p.image else "",
    } for p in products.order_by("name")[:500]]})


@require_POST
@login_required
def api_checkout(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("Некорректный чек.")
        rows = data.get("items")
        payment = data.get("payment")
        if payment not in {"cash", "card"} or not isinstance(rows, list) or not 1 <= len(rows) <= 200:
            raise ValueError("Проверьте товары и способ оплаты.")
        quantities = Counter()
        for row in rows:
            if (not isinstance(row, dict) or type(row.get("id")) is not int
                    or type(row.get("qty")) is not int or not 1 <= row["qty"] <= 10000):
                raise ValueError("Количество должно быть положительным целым числом.")
            quantities[row["id"]] += row["qty"]
        with transaction.atomic():
            shift = Shift.objects.select_for_update().filter(
                user=request.user, closed_at__isnull=True
            ).first()
            if not shift:
                raise ValueError("Сначала откройте смену.")
            products = list(Product.objects.select_for_update().filter(
                pk__in=quantities, is_active=True
            ).order_by("pk"))
            if len(products) != len(quantities):
                raise ValueError("Один из товаров недоступен.")
            for product in products:
                if quantities[product.pk] > product.stock:
                    raise ValueError(f"«{product.name}»: доступно {product.stock} шт.")
            total = sum((p.price * quantities[p.pk] for p in products), Decimal("0"))
            sale = Sale.objects.create(shift=shift, payment=payment, total=total)
            warnings = []
            for product in products:
                qty = quantities[product.pk]
                SaleItem.objects.create(sale=sale, product=product, name=product.name,
                                        price=product.price, quantity=qty)
                product.stock -= qty
                product.save(update_fields=["stock"])
                StockMovement.objects.create(product=product, user=request.user,
                    direction="sale", quantity=qty, comment=f"Чек №{sale.pk}")
                if product.stock <= product.min_stock:
                    warnings.append(f"«{product.name}»: осталось {product.stock} шт.")
        return JsonResponse({"ok": True, "sale_id": sale.pk, "total": str(total), "warnings": warnings})
    except (ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc) or "Некорректные данные."}, status=400)


def _product_totals(items):
    # Аннотация называется qty, а не quantity: поле модели не перекрывается.
    return items.order_by().values("product_id", "name").annotate(
        qty=Sum("quantity"),
        revenue=Sum(F("price") * F("quantity"),
                    output_field=DecimalField(max_digits=20, decimal_places=2)),
    )


def _shift_report_data(shift):
    sales = Sale.objects.filter(shift=shift).select_related("shift__user").order_by("created_at")
    items = []
    for row in _product_totals(SaleItem.objects.filter(sale__shift=shift)).order_by("name"):
        row["quantity"] = row["qty"]
        items.append(row)
    cash = sales.filter(payment="cash").aggregate(v=Sum("total"))["v"] or Decimal("0")
    card = sales.filter(payment="card").aggregate(v=Sum("total"))["v"] or Decimal("0")
    return {"shift": shift, "sales": sales, "items": items, "checks": sales.count(),
            "items_count": sum(row["quantity"] for row in items),
            "cash": cash, "card": card, "revenue": cash + card}


@login_required
def shift_view(request):
    current = Shift.objects.filter(user=request.user, closed_at__isnull=True).first()
    closed = Shift.objects.filter(user=request.user, closed_at__isnull=False).order_by("-closed_at").first()
    context = {**ctx(request.user), "shift": current,
               "closed_report": _shift_report_data(closed) if closed else None}
    if current:
        report = _shift_report_data(current)
        context.update({key: report[key] for key in ("sales", "checks", "items_count", "cash", "card", "revenue")})
        context["sold_items"] = report["items"]
    else:
        context.update(sales=[], sold_items=[], checks=0, items_count=0,
                       cash=0, card=0, revenue=0)
    return render(request, "core/shift.html", context)


@require_POST
@login_required
def open_shift(request):
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        if not Shift.objects.filter(user=request.user, closed_at__isnull=True).exists():
            Shift.objects.create(user=request.user)
    return redirect("shift")


@require_POST
@login_required
def close_shift(request):
    with transaction.atomic():
        shift = Shift.objects.select_for_update().filter(user=request.user, closed_at__isnull=True).first()
        if shift:
            shift.closed_at = timezone.now()
            shift.save(update_fields=["closed_at"])
    return redirect("shift")


@user_passes_test(is_admin)
def product_list(request):
    q = request.GET.get("q", "").strip()
    products = Product.objects.all()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    return render(request, "core/products.html", {**ctx(request.user), "products": products.order_by("name"), "q": q})


class ProductForm(forms.ModelForm):
    sku = forms.CharField(required=False, max_length=50, label="Артикул")
    class Meta:
        model = Product
        fields = ["name", "sku", "barcode", "category", "description", "price", "cost",
                  "stock", "min_stock", "image", "is_active", "is_public"]
    def __init__(self, *args, **kwargs):
        from django.core.validators import MinValueValidator
        super().__init__(*args, **kwargs)
        for field in ("price", "cost", "stock", "min_stock"):
            self.fields[field].validators.append(MinValueValidator(0))
            self.fields[field].widget.attrs["min"] = 0
        if self.instance.pk and (self.instance.sku or "").startswith("AUTO-"):
            self.initial["sku"] = ""
    def clean_sku(self):
        sku = self.cleaned_data.get("sku", "").strip()
        if sku:
            return sku
        old = self.instance.sku or ""
        return old if self.instance.pk and old.startswith("AUTO-") else "AUTO-" + uuid.uuid4().hex
    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and getattr(image, "size", 0) > 5 * 1024 * 1024:
            raise forms.ValidationError("Максимальный размер — 5 МБ.")
        return image


@user_passes_test(is_admin)
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk is not None else None
    form = ProductForm(request.POST if request.method == "POST" else None,
                       request.FILES if request.method == "POST" else None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("products")
    return render(request, "core/product_form.html", {**ctx(request.user), "product": product, "form": form})


product_create = product_edit


@require_POST
@user_passes_test(is_admin)
def product_delete(request, pk):
    from django.db.models.deletion import ProtectedError
    with transaction.atomic():
        product = get_object_or_404(Product.objects.select_for_update(), pk=pk)
        # Архивируем также товары, на которые ссылаются онлайн-заказы.
        if SaleItem.objects.filter(product=product).exists() or StockMovement.objects.filter(product=product).exists():
            product.is_active = False
            product.is_public = False
            product.save(update_fields=["is_active", "is_public"])
        else:
            try:
                with transaction.atomic():
                    product.delete()
            except ProtectedError:
                product.is_active = False
                product.is_public = False
                product.save(update_fields=["is_active", "is_public"])
    return redirect("products")


@user_passes_test(is_admin)
def stock_view(request):
    return render(request, "core/stock.html", {**ctx(request.user),
        "products": Product.objects.order_by("name"),
        "movements": StockMovement.objects.select_related("product", "user").order_by("-created_at")[:100]})


@require_POST
@user_passes_test(is_admin)
def stock_movement(request):
    try:
        qty = int(request.POST.get("quantity") or 0)
    except ValueError:
        qty = 0
    direction = request.POST.get("direction")
    if qty <= 0 or direction not in {"in", "out"}:
        messages.error(request, "Проверьте количество и тип операции.")
        return redirect("stock")
    with transaction.atomic():
        product = get_object_or_404(Product.objects.select_for_update(), pk=request.POST.get("product"))
        if direction == "out" and qty > product.stock:
            messages.error(request, "Недостаточно товара для списания.")
            return redirect("stock")
        product.stock += qty if direction == "in" else -qty
        product.save(update_fields=["stock"])
        StockMovement.objects.create(product=product, user=request.user, direction=direction,
                                    quantity=qty, comment=request.POST.get("comment", "")[:255])
    return redirect("stock")


def _filtered_sales(request):
    start = parse_date(request.GET.get("from", ""))
    end = parse_date(request.GET.get("to", ""))
    sales = Sale.objects.select_related("shift__user")
    if start:
        sales = sales.filter(created_at__date__gte=start)
    if end:
        sales = sales.filter(created_at__date__lte=end)
    return sales, start.isoformat() if start else "", end.isoformat() if end else ""


@user_passes_test(is_admin)
def reports(request):
    sales, date_from, date_to = _filtered_sales(request)
    product_stats = _product_totals(SaleItem.objects.filter(sale__in=sales)).order_by("-revenue")
    user_stats = sales.order_by().values("shift__user__username").annotate(
        checks=Count("id"), revenue=Sum("total")
    ).order_by("-revenue")
    return render(request, "core/reports.html", {**ctx(request.user),
        "sales": sales, "product_stats": product_stats, "user_stats": user_stats,
        "total": sales.aggregate(v=Sum("total"))["v"] or Decimal("0"),
        "from": date_from, "to": date_to})


def _excel_text(value):
    # Не допускаем интерпретацию названия товара как формулы Excel.
    value = str(value or "")
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


@user_passes_test(is_admin)
def reports_export(request):
    sales, _, _ = _filtered_sales(request)
    workbook = Workbook()
    checks = workbook.active
    checks.title = "Чеки"
    checks.append(["№ чека", "Дата и время", "Кассир", "Способ оплаты", "Сумма, ₽"])
    for sale in sales.order_by("created_at"):
        checks.append([sale.pk, timezone.localtime(sale.created_at).strftime("%d.%m.%Y %H:%M"),
            _excel_text(sale.shift.user.get_full_name() or sale.shift.user.username),
            sale.get_payment_display(), float(sale.total)])
    products = workbook.create_sheet("Проданные товары")
    products.append(["Товар", "Количество, шт.", "Выручка, ₽"])
    qty, revenue = 0, Decimal("0")
    for row in _product_totals(SaleItem.objects.filter(sale__in=sales)).order_by("name"):
        products.append([_excel_text(row["name"]), row["qty"], float(row["revenue"])])
        qty += row["qty"]
        revenue += row["revenue"]
    products.append(["ИТОГО", qty, float(revenue)])
    for cell in products[products.max_row]:
        cell.font = Font(bold=True)
    # Детализация сохраняет связь: товар — количество — способ оплаты.
    details = workbook.create_sheet("Позиции чеков")
    details.append(["№ чека", "Дата", "Кассир", "Товар", "Количество", "Цена, ₽", "Сумма, ₽", "Оплата"])
    for item in SaleItem.objects.filter(sale__in=sales).select_related("sale__shift__user").order_by("sale_id", "pk"):
        sale = item.sale
        details.append([sale.pk, timezone.localtime(sale.created_at).strftime("%d.%m.%Y %H:%M"),
            _excel_text(sale.shift.user.username), _excel_text(item.name), item.quantity,
            float(item.price), float(item.price * item.quantity), sale.get_payment_display()])
    for sheet in workbook:
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            width = max(len(str(c.value if c.value is not None else "")) for c in column) + 3
            sheet.column_dimensions[column[0].column_letter].width = min(max(width, 12), 48)
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="laserok-report.xlsx"'
    workbook.save(response)
    return response


@user_passes_test(is_admin)
def online_orders(request):
    return render(request, "core/orders.html", {**ctx(request.user),
        "orders": OnlineOrder.objects.prefetch_related("items__product").order_by("-created_at")})


@require_POST
@user_passes_test(is_admin)
def online_order_action(request, pk, action):
    # Совместимо с резервом, уже вычтенным из Product.stock при оформлении.
    with transaction.atomic():
        order = get_object_or_404(OnlineOrder.objects.select_for_update(), pk=pk)
        allowed = {"new": {"confirm", "cancel"}, "confirmed": {"complete", "cancel"}}
        if action not in allowed.get(order.status, set()):
            return redirect("online_orders")
        if action == "cancel":
            for item in order.items.order_by("product_id"):
                product = Product.objects.select_for_update().get(pk=item.product_id)
                product.stock += item.quantity
                product.save(update_fields=["stock"])
        order.status = {"confirm": "confirmed", "complete": "completed", "cancel": "cancelled"}[action]
        order.save(update_fields=["status"])
    return redirect("online_orders")


@user_passes_test(is_admin)
def employees(request):
    return render(request, "core/employees.html", {**ctx(request.user), "employees": User.objects.order_by("username")})


@user_passes_test(is_admin)
def employee_create(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if not username or not password:
            messages.error(request, "Заполните логин и пароль.")
        elif len(username) > 150 or User.objects.filter(username=username).exists():
            messages.error(request, "Логин занят или слишком длинный.")
        else:
            employee = User.objects.create_user(username=username, password=password,
                first_name=request.POST.get("first_name", "")[:150], last_name=request.POST.get("last_name", "")[:150])
            employee.is_staff = employee.is_superuser = bool(request.POST.get("is_admin"))
            employee.save()
            return redirect("employees")
    return render(request, "core/employee_form.html", {**ctx(request.user), "employee": None})


@user_passes_test(is_admin)
def employee_edit(request, pk):
    employee = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        if not username or len(username) > 150 or User.objects.exclude(pk=pk).filter(username=username).exists():
            messages.error(request, "Проверьте логин: он пуст, занят или слишком длинный.")
        else:
            employee.username = username
            employee.first_name = request.POST.get("first_name", "")[:150]
            employee.last_name = request.POST.get("last_name", "")[:150]
            admin = bool(request.POST.get("is_admin"))
            # Не снимаем полный доступ с собственной записи случайным кликом.
            if employee.pk == request.user.pk and is_admin(request.user):
                admin = True
            employee.is_staff = employee.is_superuser = admin
            if not admin:
                employee.groups.remove(*employee.groups.filter(name="Администраторы"))
            password = request.POST.get("password", "")
            if password:
                employee.set_password(password)
            employee.save()
            if password and employee.pk == request.user.pk:
                update_session_auth_hash(request, employee)
            return redirect("employees")
    return render(request, "core/employee_form.html", {**ctx(request.user), "employee": employee})
