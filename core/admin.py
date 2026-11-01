from django.contrib import admin
from .models import *
admin.site.register([Product, Shift, Sale, SaleItem, StockMovement, OnlineOrder, OnlineOrderItem])
