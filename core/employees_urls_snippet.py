# Добавьте эти маршруты в urlpatterns в core/urls.py
path("employees/", views.employees, name="employees"),
path("employees/new/", views.employee_create, name="employee_create"),
path("employees/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
