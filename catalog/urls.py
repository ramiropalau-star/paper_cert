from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.equivalence_table, name="equivalences"),
    path("resolve/", views.catalog_resolve, name="resolve"),
    path("entities/new/", views.entity_create, name="entity_new"),
    path("entities/<int:pk>/", views.entity_detail, name="entity_detail"),
    path("entities/<int:pk>/update/", views.entity_update, name="entity_update"),
    path(
        "entities/<int:pk>/aliases/add/",
        views.entity_alias_add,
        name="alias_add",
    ),
    path(
        "entities/<int:entity_pk>/exams/add/",
        views.exam_create,
        name="exam_create",
    ),
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
