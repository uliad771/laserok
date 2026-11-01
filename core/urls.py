from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from . import green_views
from . import pos_catalog_fix
from . import product_editor


urlpatterns = [
    # Главная и авторизация
    path("", views.home, name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="core/login.html",
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    # Касса
    path("pos/", green_views.pos, name="pos"),
    path(
        "api/pos-catalog/",
        pos_catalog_fix.pos_catalog,
        name="pos_catalog_fixed",
    ),
    path(
        "api/products/",
        green_views.products_api,
        name="api_products",
    ),
    path(
        "api/checkout/",
        green_views.checkout,
        name="api_checkout",
    ),

    # Смены
    path("shift/", views.shift_view, name="shift"),
    path("shift/open/", views.open_shift, name="open_shift"),
    path("shift/close/", views.close_shift, name="close_shift"),

    # Товары
    path("products/", views.product_list, name="products"),
    path(
        "products/new/",
        product_editor.product_edit,
        name="product_new",
    ),
    path(
        "products/<int:pk>/edit/",
        product_editor.product_edit,
        name="product_edit",
    ),
    path(
        "products/<int:pk>/delete/",
        views.product_delete,
        name="product_delete",
    ),

    # Склад
    path("stock/", views.stock_view, name="stock"),
    path(
        "stock/movement/",
        views.stock_movement,
        name="stock_movement",
    ),

    # Отчёты
    path("reports/", views.reports, name="reports"),
    path(
        "reports/export/",
        views.reports_export,
        name="reports_export",
    ),

    # Онлайн-заказы
    path("orders/", views.online_orders, name="online_orders"),
    path(
        "orders/<int:pk>/<str:action>/",
        views.online_order_action,
        name="online_order_action",
    ),

    # Сотрудники
    path("employees/", views.employees, name="employees"),
    path(
        "employees/new/",
        views.employee_create,
        name="employee_create",
    ),
    path(
        "employees/<int:pk>/edit/",
        views.employee_edit,
        name="employee_edit",
    ),
]