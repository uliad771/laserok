from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404


def is_admin(user):
    return user.is_superuser or user.groups.filter(name="Администраторы").exists()


@user_passes_test(is_admin)
def employees(request):
    return render(request, "core/employees.html", {
        "employees": User.objects.order_by("username"),
        "is_admin": True,
    })


@user_passes_test(is_admin)
def employee_create(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if not username or not password:
            messages.error(request, "Заполните логин и пароль.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Такой логин уже существует.")
        else:
            employee = User.objects.create_user(
                username=username,
                password=password,
                first_name=request.POST.get("first_name", "").strip(),
                last_name=request.POST.get("last_name", "").strip(),
            )
            if request.POST.get("is_admin"):
                employee.is_staff = True
                employee.is_superuser = True
                employee.save()
            return redirect("employees")
    return render(request, "core/employee_form.html", {"employee": None, "is_admin": True})


@user_passes_test(is_admin)
def employee_edit(request, pk):
    employee = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        employee.username = request.POST.get("username", "").strip()
        employee.first_name = request.POST.get("first_name", "").strip()
        employee.last_name = request.POST.get("last_name", "").strip()
        employee.is_staff = bool(request.POST.get("is_admin"))
        employee.is_superuser = bool(request.POST.get("is_admin"))
        password = request.POST.get("password", "")
        if password:
            employee.set_password(password)
        employee.save()
        return redirect("employees")
    return render(request, "core/employee_form.html", {"employee": employee, "is_admin": True})
