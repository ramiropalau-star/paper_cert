from django.urls import path

from documents import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("queue/", views.document_queue, name="queue"),
    path("gallery/", views.document_gallery, name="gallery"),
    path("bulk-review/", views.bulk_review, name="bulk_review"),
    path("upload/", views.upload, name="upload"),
    path("<int:pk>/", views.review_detail, name="detail"),
    path("<int:pk>/edit/", views.review_edit, name="edit"),
    path("<int:pk>/validate/", views.review_validate, name="validate"),
    path("<int:pk>/approve/", views.review_approve, name="approve"),
    path("<int:pk>/reject/", views.review_reject, name="reject"),
    path("<int:pk>/release-field/", views.review_release_field, name="release_field"),
    path("<int:pk>/reprocess/", views.review_reprocess, name="reprocess"),
    path("<int:pk>/re-extract/", views.review_reextract, name="re_extract"),
    path("<int:pk>/teach-alias/", views.review_teach_alias, name="teach_alias"),
    path("<int:pk>/verify-source/", views.review_verify_source, name="verify_source"),
    path("field-aliases/", views.field_alias_list, name="field_aliases"),
    path("<int:pk>/original/", views.document_original, name="original"),
    path("<int:pk>/thumbnail/", views.document_thumbnail, name="thumbnail"),
    path("<int:pk>/history/", views.review_history, name="history"),
    path("<int:pk>/status/", views.document_status, name="status"),
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("delete-all/", views.delete_all, name="delete_all"),
]
