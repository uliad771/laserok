from django.conf import settings
from django.db import models
from django.utils import timezone


class Product(models.Model):
    name = models.CharField("Название", max_length=200)
    sku = models.CharField("Артикул", max_length=50, unique=True)
    barcode = models.CharField("Штрихкод", max_length=64, blank=True)
    category = models.CharField("Категория", max_length=100, blank=True)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2)
    cost = models.DecimalField("Себестоимость", max_digits=10, decimal_places=2, default=0)
    stock = models.PositiveIntegerField("Остаток", default=0)
    min_stock = models.PositiveIntegerField("Минимальный запас", default=3)
    emoji = models.CharField("Иконка", max_length=8, default="📦", blank=True)
    image = models.ImageField("Фото товара", upload_to="products/%Y/%m/", blank=True, null=True)
    is_active = models.BooleanField("Активен", default=True)
    is_public = models.BooleanField("Показывать на витрине", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_low(self):
        return self.stock <= self.min_stock


class Shift(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts")
    started_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cash_start = models.DecimalField("Стартовый остаток", max_digits=10, decimal_places=2, default=0)

    @property
    def is_open(self):
        return self.closed_at is None


class Sale(models.Model):
    PAYMENT_CHOICES = [("cash", "Наличные"), ("card", "Карта / СБП")]
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="sales")
    created_at = models.DateTimeField(auto_now_add=True)
    payment = models.CharField("Оплата", max_length=10, choices=PAYMENT_CHOICES)
    total = models.DecimalField("Сумма", max_digits=12, decimal_places=2, default=0)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.quantity


class StockMovement(models.Model):
    DIRECTIONS = [("in", "Оприходование"), ("out", "Списание"), ("sale", "Продажа"), ("return", "Возврат")]
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    direction = models.CharField(max_length=10, choices=DIRECTIONS)
    quantity = models.PositiveIntegerField()
    comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OnlineOrder(models.Model):
    STATUS_CHOICES = [("new", "Новый"), ("confirmed", "Подтверждён"), ("completed", "Выполнен"), ("cancelled", "Отменён")]
    number = models.CharField(max_length=20, unique=True)
    customer_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32)
    email = models.EmailField(blank=True)
    delivery = models.CharField(max_length=100, default="Самовывоз")
    address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class OnlineOrderItem(models.Model):
    order = models.ForeignKey(OnlineOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
