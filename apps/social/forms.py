from django import forms
from social.models import Underline


class UnderlineForm(forms.ModelForm):
    start = forms.IntegerField(widget=forms.HiddenInput)
    end = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = Underline
        exclude = ['book', 'user', 'comment']


class UnderlineCommentForm(forms.Form):
    underline_id = forms.IntegerField(widget=forms.HiddenInput)
    comment = forms.CharField(
        widget=forms.Textarea(attrs={"cols": '30', "rows": "2"}),
        required=False)
    