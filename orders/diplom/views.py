import yaml
from django.http import JsonResponse
from django.db.models import F, Sum
from django.contrib.auth import login, authenticate
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from orders.diplom.permissions import IsShop
from orders.diplom.models import (
    Shop,
    Category,
    Product,
    ProductInfo,
    Parameter,
    ProductParameter,
    Order,
    Contact,
    User,
)
from orders.diplom.serializers import (
    ShopSerializer,
    CategorySerializer,
    ProductSerializer,
    OrderSerializer,
    OrderInfoSerializer,
    OrderItemSerializer,
)


class UserRegisterView(APIView):
    def post(self, request, *args, **kwargs):
        user = User.objects.create(
            email=request.data["email"],
            password=request.data["password"],
            username=request.data["username"],
            full_name=request.data["full_name"],
            type=request.data["type"],
            company=request.data["company"],
            position=request.data["position"],
        )
        user.set_password(request.data["password"])
        user.save()
        # send_registration_email_task.delay(request.user.id)
        return JsonResponse({"Status": True})


class Login(APIView):
    def post(self, request, *args, **kwargs):
        user = authenticate(
            request,
            username=request.data["username"],
            password=request.data["password"],
        )
        if user is not None:
            if user.is_active:
                login(request, user)
                return JsonResponse(
                    {"status": True, "you are now logged in as": request.user.username}
                )
        else:
            return JsonResponse({"status": "invalid data"})


class ContactView(APIView):
    def post(self, request, *args, **kwargs):
        contact = Contact.objects.create(
            user=request.user,
            city=request.data["city"],
            street=request.data["street"],
            house=request.data["house"],
            structure=request.data["structure"],
            building=request.data["building"],
            apartment=request.data["apartment"],
            phone=request.data["phone"],
        )
        contact.save()
        return JsonResponse({"status": "success"})


class SupplierUpdate(APIView):
    permission_classes = [IsAuthenticated & IsShop]

    def post(self, request, file_name):
        with open(f"data/{file_name}", "r", encoding="UTF-8") as stream:
            data = yaml.safe_load(stream)
            shop, created = Shop.objects.get_or_create(name=data["shop"])
            for category in data["categories"]:
                category_object, created = Category.objects.get_or_create(
                    id=category["id"], name=category["name"]
                )
                category_object.shops.add(shop.id)
                category_object.save()
            for product in data["goods"]:
                product_object, created = Product.objects.get_or_create(
                    name=product["name"], category_id=product["category"]
                )
                product_info = ProductInfo.objects.create(
                    product_id=product_object.id,
                    shop_id=shop.id,
                    external_id=product["id"],
                    model=product["model"],
                    quantity=product["quantity"],
                    price=product["price"],
                    price_rrc=product["price_rrc"],
                )
                for key, value in product["parameters"].items():
                    parameter_object, created = Parameter.objects.get_or_create(
                        name=key
                    )
                    ProductParameter.objects.create(
                        product_info_id=product_info.id,
                        parameter_id=parameter_object.id,
                        value=value,
                    )
        return JsonResponse({"status": "products added successfully"})


class ShopView(ReadOnlyModelViewSet):
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
    permission_classes = [IsAuthenticated]
    filterset_backends = [DjangoFilterBackend]
    filterset_fields = ["state"]


class CategoryView(ReadOnlyModelViewSet):
    queryset = Category.objects.prefetch_related("shops").all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filterset_backends = [DjangoFilterBackend]
    filterset_fields = ["shops"]


class ProductView(ReadOnlyModelViewSet):
    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    filterset_backends = [DjangoFilterBackend]
    filterset_fields = ["category"]


class OrderView(ReadOnlyModelViewSet):
    queryset = Order.objects.annotate(
        total_sum=Sum(
            F("order_items__quantity") * F("order_items__product_info__price")
        )
    )
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    detail_serializer_class = OrderInfoSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            return (
                queryset.filter(user=self.request.user)
                .exclude(state="basket")
                .prefetch_related("contact", "order_items__product_info")
                .all()
            )
        elif self.action == "retrieve":
            return (
                queryset.filter(user=self.request.user)
                .exclude(state="basket")
                .prefetch_related(
                    "order_items__product_info__product__category",
                    "user",
                    "order_items__product_info__product_parameters__parameter",
                    "contact",
                )
                .all()
            )

    def get_serializer_class(self):
        if self.action == "retrieve":
            if hasattr(self, "detail_serializer_class"):
                return self.detail_serializer_class

        return super(OrderView, self).get_serializer_class()


class OrderCreationView(APIView):
    def post(self, request, *args, **kwargs):
        permission_classes = [IsAuthenticated]
        order = Order.objects.create(user=request.user, state="basket")
        for order_item in request.data:
            order_item.update({"order": order.id})
            serializer = OrderItemSerializer(data=order_item)
            if serializer.is_valid():
                serializer.save()
            else:
                return JsonResponse({"Status": False, "Errors": serializer.errors})
        return JsonResponse({"Status": True})


class BasketView(APIView):
    def patch(self, request, *args, **kwargs):
        permission_classes = [IsAuthenticated]
        contact = Contact.objects.get(id=request.data["contacts"])
        order = Order.objects.get(user_id=request.user.id, state="basket")
        order.contact = contact
        order.state = "new"
        order.save()
        return JsonResponse({"Status": True})
        # return redirect("order_confirmation")


class OrderConfirmationView(APIView):
    def post(self, request, *args, **kwargs):
        permission_classes = [IsAuthenticated]
        order = Order.objects.get(user_id=request.user.id, state="new")
        action = request.data["action"]
        if action == "approve":
            order.state = "confirmed"
            order.save()
            # send_order_email_task.delay(request.user.id)
            return JsonResponse({"Status": True})
        elif action == "disapprove":
            return JsonResponse({"Status": "Now you can change your order"})