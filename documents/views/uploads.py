"""Upload and deletion views."""

import logging
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.permissions import ROLE_ADMIN, ROLE_VIEWER, role_required
from documents.models import Document
from documents.services.intake import process_upload
from documents.services.paperless import PaperlessError, build_document_store

logger = logging.getLogger("documents.views")

DELETE_ALL_CONFIRM = "DELETE-UNTRACKED"
DELETE_ALL_SCOPES = {"tracked", "untracked"}


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET", "POST"])
def upload(request):
    if request.method == "POST":
        uploads = request.FILES.getlist("document")
        if not uploads:
            messages.error(request, "Seleccioná al menos un archivo para subir.")
            return redirect("documents:upload")

        stored = duplicates = 0
        for uploaded in uploads:
            declared_type = (
                uploaded.content_type
                or mimetypes.guess_type(uploaded.name)[0]
                or "application/octet-stream"
            )
            result = process_upload(
                uploaded.read(),
                uploaded.name,
                declared_type,
                user=request.user,
            )
            if result.error:
                messages.error(request, f"{uploaded.name}: {result.error}")
            elif result.duplicate:
                duplicates += 1
            else:
                stored += 1
        if stored:
            messages.success(
                request, f"{stored} archivo(s) almacenado(s) y en cola de procesamiento."
            )
        if duplicates:
            messages.info(request, f"{duplicates} archivo(s) ya estaban procesados.")
        return redirect("documents:upload")

    return render(request, "documents/upload.html")


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET", "POST"])
def delete(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    if request.method == "GET":
        return render(request, "documents/delete.html", {"document": document})

    if document.paperless_document_id:
        store = build_document_store()
        try:
            store.delete_document(document.paperless_document_id)
        except PaperlessError as exc:
            messages.error(
                request,
                f"No se pudo eliminar el original en Paperless: {exc}",
            )
            return redirect("documents:delete", pk=document.pk)
        finally:
            store.close()

    document.delete()
    messages.success(request, "Documento y datos asociados eliminados.")
    return redirect("home")


def _tracked_paperless_ids() -> set[str]:
    return {
        str(pk)
        for pk in Document.objects.exclude(paperless_document_id="").values_list(
            "paperless_document_id", flat=True
        )
    }


def _delete_remote_documents(store, remote_ids) -> tuple[int, list[str]]:
    deleted = 0
    errors = []
    for remote_id in remote_ids:
        try:
            store.delete_document(remote_id)
            deleted += 1
        except PaperlessError as exc:
            errors.append(f"#{remote_id}: {exc}")
    return deleted, errors


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET", "POST"])
def delete_all(request):
    """Scoped bulk deletion.

    ``scope=tracked`` (default) removes Django records and the Paperless
    originals the application tracks. ``scope=untracked`` removes only
    Paperless documents the application does not track and requires a typed
    confirmation. Both paths emit a structured ``bulk_delete`` audit event.
    """
    if request.method == "GET":
        untracked_count = None
        store = build_document_store()
        try:
            remote_ids = {str(item.get("id")) for item in store.list_documents() if item.get("id")}
            untracked_count = len(remote_ids - _tracked_paperless_ids())
        except PaperlessError:
            untracked_count = None
        finally:
            store.close()
        return render(
            request,
            "documents/delete_all.html",
            {
                "count": Document.objects.count(),
                "untracked_count": untracked_count,
                "confirm_token": DELETE_ALL_CONFIRM,
            },
        )

    scope = request.POST.get("scope") or "tracked"
    if scope not in DELETE_ALL_SCOPES:
        messages.error(request, "Scope de eliminación no válido.")
        return redirect("documents:delete_all")

    if scope == "untracked" and request.POST.get("confirm") != DELETE_ALL_CONFIRM:
        messages.error(
            request,
            f"Para eliminar documentos no rastreados escribí "
            f"«{DELETE_ALL_CONFIRM}» en el campo de confirmación.",
        )
        return redirect("documents:delete_all")

    document_count = Document.objects.count()
    store = build_document_store()
    paperless_errors = []
    paperless_deleted = 0
    try:
        if scope == "untracked":
            remote_ids = [str(item.get("id")) for item in store.list_documents() if item.get("id")]
            untracked_ids = [
                remote_id for remote_id in remote_ids if remote_id not in _tracked_paperless_ids()
            ]
            paperless_deleted, remote_errors = _delete_remote_documents(store, untracked_ids)
            paperless_errors.extend(remote_errors)
        else:
            tracked_ids = sorted(_tracked_paperless_ids())
            paperless_deleted, remote_errors = _delete_remote_documents(store, tracked_ids)
            paperless_errors.extend(remote_errors)
            Document.objects.all().delete()
    except PaperlessError as exc:
        paperless_errors.append(str(exc))
    finally:
        store.close()

    logger.info(
        "bulk_delete",
        extra={
            "actor": request.user.get_username(),
            "scope": scope,
            "document_count": document_count if scope == "tracked" else 0,
            "untracked_count": paperless_deleted if scope == "untracked" else 0,
            "paperless_deleted": paperless_deleted,
            "paperless_errors": len(paperless_errors),
        },
    )

    if scope == "untracked":
        if paperless_errors:
            messages.warning(
                request,
                f"{paperless_deleted} documentos no rastreados eliminados, pero "
                f"{len(paperless_errors)} fallaron: {'; '.join(paperless_errors[:3])}",
            )
        else:
            messages.success(
                request,
                f"Eliminados {paperless_deleted} documentos no rastreados de Paperless.",
            )
        return redirect("documents:list")

    if paperless_errors:
        messages.warning(
            request,
            f"Registros Django eliminados ({document_count}), pero "
            f"{len(paperless_errors)} originales de Paperless fallaron: "
            f"{'; '.join(paperless_errors[:3])}",
        )
    else:
        messages.success(
            request,
            f"Eliminados {document_count} documentos de Django y "
            f"{paperless_deleted} originales de Paperless.",
        )
    return redirect("documents:list")
