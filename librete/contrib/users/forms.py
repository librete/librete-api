from django import forms
from django.conf import settings
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class SignupForm(forms.Form):
    """Extra, optional sign-up fields. allauth mixes these into its headless signup input."""

    first_name = forms.CharField(label=_("First name"), max_length=150, required=False)
    last_name = forms.CharField(label=_("Last name"), max_length=150, required=False)
    language = forms.ChoiceField(label=_("Language"), choices=settings.LANGUAGES, required=False)

    def signup(self, request, user):
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        language = self.cleaned_data.get("language") or get_language()
        if language not in dict(settings.LANGUAGES):
            language = settings.LANGUAGE_CODE
        user.language = language
        user.save()
