# FILE PURPOSE: Staff screens for application records, including safeguards around ownership and
# share secrets.
# Import admin from django.contrib (Django framework/database/security helpers).
from django.contrib import admin

# Import Collection, CollectionMembership, PublicShare, RecentTitle, SavedTitle from
# library.models (our personal-library layer).
from library.models import Collection, CollectionMembership, PublicShare, RecentTitle, SavedTitle


@admin.register(SavedTitle)
class SavedTitleAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 4 entries.
    list_display = ["user", "title", "watched", "saved_at"]
    # Set list_filter: build an ordered list of 1 entries.
    list_filter = ["watched"]
    # Set autocomplete_fields: build an ordered list of 0 entries.
    autocomplete_fields = []

    def save_model(self, request, obj, form, change):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; obj = argument supplied by the caller; form = argument supplied by the caller;
        # change = argument supplied by the caller.
        # Import timezone from django.utils (Django framework/database/security helpers).
        from django.utils import timezone

        # Enter this branch only when change and
        # SavedTitle.objects.filter(pk=obj.pk).exclude(user_id=obj.user_id).exists(). Otherwise
        # execution uses its alternative or continues below.
        if change and SavedTitle.objects.filter(pk=obj.pk).exclude(user_id=obj.user_id).exists():
            # Import PermissionDenied from django.core.exceptions (Django
            # framework/database/security helpers).
            from django.core.exceptions import PermissionDenied

            # Raise PermissionDenied; normal execution of this block stops here.
            raise PermissionDenied("Saved title ownership cannot be reassigned.")
        # Set obj.watched_at: choose obj.watched_at or timezone.now() when obj.watched; otherwise
        # use None.
        obj.watched_at = (obj.watched_at or timezone.now()) if obj.watched else None
        # Call super().save_model with the inputs shown; its definition explains the checks, side
        # effects and return value.
        super().save_model(request, obj, form, change)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 3 entries.
    list_display = ["name", "user", "updated_at"]
    # Set search_fields: build an ordered list of 2 entries.
    search_fields = ["name", "user__email"]

    def delete_queryset(self, request, queryset):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; queryset = argument supplied by the caller.
        # Import timezone from django.utils (Django framework/database/security helpers).
        from django.utils import timezone

        # Import GuestCollectionMapping from library.models (our personal-library layer).
        from library.models import GuestCollectionMapping

        # Write these fields directly on the matching rows through the orm.
        GuestCollectionMapping.objects.filter(collection__in=queryset).update(
            deleted_at=timezone.now()
        )
        # Call super().delete_queryset with the inputs shown; its definition explains the checks,
        # side effects and return value.
        super().delete_queryset(request, queryset)


@admin.register(CollectionMembership)
class MembershipAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 3 entries.
    list_display = ["collection", "saved_title", "added_at"]

    def save_model(self, request, obj, form, change):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; obj = argument supplied by the caller; form = argument supplied by the caller;
        # change = argument supplied by the caller.
        # Enter this branch only when obj.collection.user_id != obj.saved_title.user_id. Otherwise
        # execution uses its alternative or continues below.
        if obj.collection.user_id != obj.saved_title.user_id:
            # Import PermissionDenied from django.core.exceptions (Django
            # framework/database/security helpers).
            from django.core.exceptions import PermissionDenied

            # Raise PermissionDenied; normal execution of this block stops here.
            raise PermissionDenied("Collection and saved title must have the same owner.")
        # Call super().save_model with the inputs shown; its definition explains the checks, side
        # effects and return value.
        super().save_model(request, obj, form, change)


@admin.register(PublicShare)
class PublicShareAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 4 entries.
    list_display = ["collection", "enabled", "created_at", "revoked_at"]
    # fields holds the safe field-to-message mapping that the browser can display. Next, build an
    # ordered list of 4 entries.
    fields = ["collection", "enabled", "created_at", "revoked_at"]
    # Set readonly_fields: reuse fields, which was prepared earlier in this function.
    readonly_fields = fields

    def has_add_permission(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Return False to report that this predicate/check did not pass.
        return False


# Call admin.site.register with the inputs shown; its definition explains the checks, side effects
# and return value.
admin.site.register(RecentTitle)
