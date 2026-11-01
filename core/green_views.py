import json
from collections import Counter
from decimal import Decimal
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django import forms
from .models import Product, Shift, Sale, SaleItem, StockMovement


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="Администраторы").exists())


class ProductForm(forms.ModelForm):
    # Для совместимости со старым unique=True пустой артикул заменяется
    # внутренним уникальным значением. Пользователь вводить его не обязан.
    sku = forms.CharField(required=False, label="Артикул", max_length=50)
    class Meta:
        model = Product
        fields = ["name", "sku", "barcode", "category", "description", "price",
                  "cost", "stock", "min_stock", "image", "is_active", "is_public"]
        labels = {"name":"Название", "barcode":"Штрихкод", "category":"Категория",
                  "description":"Описание", "price":"Цена", "cost":"Себестоимость",
                  "stock":"Доступный остаток", "min_stock":"Минимальный запас",
                  "image":"Фото", "is_active":"Активен", "is_public":"Показывать на витрине"}
        widgets = {"description": forms.Textarea(attrs={"rows":3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ["price", "cost", "stock", "min_stock"]:
            self.fields[field].min_value = 0
            self.fields[field].widget.attrs["min"] = 0
        if self.instance.pk and self.instance.sku.startswith("AUTO-"):
            self.initial["sku"] = ""

    def clean_sku(self):
        import uuid
        value = self.cleaned_data.get("sku", "").strip()
        if not value:
            if self.instance.pk and self.instance.sku.startswith("AUTO-"):
                return self.instance.sku
            return "AUTO-" + uuid.uuid4().hex
        return value

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size") and image.size > 5*1024*1024:
            raise forms.ValidationError("Максимальный размер фотографии — 5 МБ.")
        return image


@login_required
def pos(request):
    return render(request, "core/pos.html", {"is_admin":is_admin(request.user), "active":"pos"})


@login_required
def products_api(request):
    from django.db.models import Q
    q = request.GET.get("q", "").strip()
    qs = Product.objects.filter(is_active=True)
    if q:
        qs = qs.filter(Q(name__icontains=q)|Q(sku__icontains=q)|Q(barcode=q))
    return JsonResponse({"products":[{"id":p.pk,"name":p.name,"price":str(p.price),
        "stock":p.stock,"min_stock":p.min_stock,"image":p.image.url if p.image else ""}
        for p in qs.order_by("name")[:200]]})


@require_POST
@login_required
def checkout(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("Некорректный чек.")
        rows, payment = data.get("items"), data.get("payment")
        if payment not in {"cash", "card"} or not isinstance(rows,list) or not 1<=len(rows)<=200:
            raise ValueError("Проверьте чек и способ оплаты.")
        counts = Counter()
        for row in rows:
            if not isinstance(row,dict) or type(row.get("id")) is not int or type(row.get("qty")) is not int or not 1<=row["qty"]<=10000:
                raise ValueError("Количество должно быть положительным целым числом.")
            counts[row["id"]] += row["qty"]
        with transaction.atomic():
            # Закрытие смены также должно использовать блокировку Shift
            # для полной защиты от одновременного закрытия и продажи.
            shift = Shift.objects.select_for_update().filter(user=request.user,closed_at__isnull=True).first()
            if not shift:
                raise ValueError("Сначала откройте смену.")
            products = list(Product.objects.select_for_update().filter(pk__in=counts,is_active=True).order_by("pk"))
            if len(products)!=len(counts):
                raise ValueError("Один из товаров недоступен. Обновите каталог.")
            # Все проверки выполняются ДО создания чека и списания.
            for p in products:
                if counts[p.pk]>p.stock:
                    raise ValueError(f"«{p.name}»: доступно только {p.stock} шт.")
            total = sum((p.price*counts[p.pk] for p in products),Decimal("0"))
            sale = Sale.objects.create(shift=shift,payment=payment,total=total)
            warnings=[]
            for p in products:
                qty=counts[p.pk]
                SaleItem.objects.create(sale=sale,product=p,name=p.name,price=p.price,quantity=qty)
                p.stock-=qty
                p.save(update_fields=["stock"])
                StockMovement.objects.create(product=p,user=request.user,direction="sale",quantity=qty,comment=f"Чек №{sale.pk}")
                if p.stock<=p.min_stock:
                    warnings.append(f"«{p.name}»: осталось {p.stock} шт., минимум {p.min_stock} шт.")
        return JsonResponse({"ok":True,"sale_id":sale.pk,"total":str(total),"warnings":warnings})
    except (ValueError, TypeError) as exc:
        return JsonResponse({"error":str(exc) or "Некорректные данные."},status=400)


@user_passes_test(is_admin)
def product_edit(request,pk=None):
    product=get_object_or_404(Product,pk=pk) if pk is not None else None
    form=ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method=="POST" and form.is_valid():
        form.save()
        return redirect("products")
    return render(request,"core/product_form.html",{"form":form,"product":product,"is_admin":True,"active":"products"})
