from django.http import JsonResponse


def list_orders(request):
    page = int(request.GET.get("page", "1"))
    limit = int(request.GET.get("limit", "25"))
    ordering = request.GET.get("ordering", "created_at")
    return JsonResponse({"page": page, "limit": limit, "ordering": ordering})