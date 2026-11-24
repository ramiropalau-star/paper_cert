from django.urls import path

from reports import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("<int:pk>/", views.report_detail, name="detail"),
    path("<int:pk>/status.json", views.report_status, name="status"),
    path("<int:pk>/download/", views.report_download, name="download"),
]
