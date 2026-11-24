from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.equivalence_table, name="equivalences"),
    path("entities/new/", views.entity_create, name="entity_new"),
    path(
        "equivalences/<int:pk>/update/",
        views.equivalence_update,
        name="equivalence_update",
    ),
    path(
        "exams/<int:exam_id>/equivalences/add/",
        views.equivalence_add,
        name="equivalence_add",
    ),
]
