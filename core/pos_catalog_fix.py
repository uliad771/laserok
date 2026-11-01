from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from .models import Product

@login_required
def pos_catalog(request):
    # Не используем is_public: кассе доступны все активные товары.
    q = request.GET.get("q", "").strip()
    products = Product.objects.filter(is_active=True)
    if q:
        products = products.filter(Q(name__icontains=q)|Q(sku__icontains=q)|Q(barcode=q))
    rows = []
    for p in products.order_by("name")[:500]:
        image = ""
        if p.image:
            try:
                image = p.image.url
            except ValueError:
                pass
        rows.append({"id":p.pk,"name":p.name,"price":str(p.price),
            "stock":p.stock,"min_stock":p.min_stock,"image":image})
    return JsonResponse({"products":rows})
