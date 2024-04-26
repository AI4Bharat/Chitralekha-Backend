# from django.contrib import admin
# from .models import OnboardOrganisationAccount

# admin.site.register(OnboardOrganisationAccount)


from django.contrib import admin
from .models import OnboardOrganisationAccount


class OnboardOrganisationAccountAdmin(admin.ModelAdmin):
    """
    TaskAdmin class to render the OnboardOrganisationAccount admin panel.
    """

    list_display = (
        "id",
        "orgname",
        "org_portal",
        "email",
        "org_type",
        "phone",
        "status",
        "interested_in",
        "src_language",
        "tgt_language",
        "purpose",
        "source",
        "notes",
    )
    search_fields = ("email", "status")


admin.site.register(OnboardOrganisationAccount, OnboardOrganisationAccountAdmin)
