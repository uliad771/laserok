import uuid
from decimal import Decimal
from django import forms
from django.contrib.auth.decorators import user_passes_test
from django.core.validators import MinValueValidator
from django.shortcuts import get_object_or_404, redirect, render
from .models import Product


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="Администраторы").exists())


class ProductEditorForm(forms.ModelForm):
    sku = forms.CharField(label="Артикул", max_length=50, required=False,
        help_text="Можно оставить пустым. Система присвоит внутренний номер.")

    class Meta:
        model = Product
        fields = ["name", "sku", "barcode", "category", "description", "price", "cost",
                  "stock", "min_stock", "image", "is_active", "is_public"]
        labels = {"name":"Название товара", "barcode":"Штрихкод", "category":"Категория",
            "description":"Описание", "price":"Розничная цена, ₽", "cost":"Себестоимость, ₽",
            "stock":"Доступный остаток, шт.", "min_stock":"Минимальный запас, шт.",
            "image":"Фотография", "is_active":"Активен — доступен в кассе",
            "is_public":"Показывать на публичной витрине"}
        widgets = {"description":forms.Textarea(attrs={"rows":4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["price", "cost", "stock", "min_stock"]:
            self.fields[name].validators.append(MinValueValidator(0))
            self.fields[name].widget.attrs["min"] = "0"
        for name in ["price", "cost"]:
            self.fields[name].widget.attrs["step"] = "0.01"
        if self.instance.pk and self.instance.sku.startswith("AUTO-"):
            self.initial["sku"] = ""

    def clean_sku(self):
        value = self.cleaned_data.get("sku", "").strip()
        if value:
            return value
        if self.instance.pk and self.instance.sku.startswith("AUTO-"):
            return self.instance.sku
        return "AUTO-" + uuid.uuid4().hex

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and getattr(image, "size", 0) > 5*1024*1024:
            raise forms.ValidationError("Максимум 5 МБ.")
        uploaded = self.files.get("image")
        if uploaded and getattr(uploaded, "image", None) and uploaded.image.format not in {"JPEG","PNG","WEBP"}:
            raise forms.ValidationError("Используйте JPG, PNG или WebP.")
        return image


@user_passes_test(is_admin)
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk is not None else None
    # Всегда передаём form в шаблон, включая GET и невалидный POST.
    if request.method == "POST":
        form = ProductEditorForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            return redirect("products")
    else:
        form = ProductEditorForm(instance=product)
    return render(request, "core/product_form.html", {
        "form": form, "product": product, "is_admin": True, "active": "products",
    })


# Для проектов с отдельным обработчиком создания товара.
product_create = product_edit
