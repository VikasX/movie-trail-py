from django.contrib import admin

from library.models import Collection, CollectionMembership, PublicShare, RecentTitle, SavedTitle


@admin.register(SavedTitle)
class SavedTitleAdmin(admin.ModelAdmin):
    list_display = ["user", "title", "watched", "saved_at"]
    list_filter = ["watched"]
    autocomplete_fields = []

    def save_model(self, request, obj, form, change):
        from django.utils import timezone

        if change and SavedTitle.objects.filter(pk=obj.pk).exclude(user_id=obj.user_id).exists():
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Saved title ownership cannot be reassigned.")
        obj.watched_at = (obj.watched_at or timezone.now()) if obj.watched else None
        super().save_model(request, obj, form, change)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "updated_at"]
    search_fields = ["name", "user__email"]

    def delete_queryset(self, request, queryset):
        from django.utils import timezone

        from library.models import GuestCollectionMapping

        GuestCollectionMapping.objects.filter(collection__in=queryset).update(
            deleted_at=timezone.now()
        )
        super().delete_queryset(request, queryset)


@admin.register(CollectionMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["collection", "saved_title", "added_at"]

    def save_model(self, request, obj, form, change):
        if obj.collection.user_id != obj.saved_title.user_id:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Collection and saved title must have the same owner.")
        super().save_model(request, obj, form, change)


@admin.register(PublicShare)
class PublicShareAdmin(admin.ModelAdmin):
    list_display = ["collection", "enabled", "created_at", "revoked_at"]
    fields = ["collection", "enabled", "created_at", "revoked_at"]
    readonly_fields = fields

    def has_add_permission(self, request):
        return False


admin.site.register(RecentTitle)
