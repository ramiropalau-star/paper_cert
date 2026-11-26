from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("", views.user_list, name="user_list"),
    path("new/", views.user_create, name="user_create"),
    path("<int:pk>/", views.user_edit, name="user_edit"),
]
