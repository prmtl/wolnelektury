from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from catalogue.models import Book
from social.forms import UnderlineForm, UnderlineCommentForm
from social.models import Underline
from django.contrib.auth.decorators import login_required


@login_required
@require_POST
def underline(request, slug):
    book = get_object_or_404(Book, slug=slug)

    form = UnderlineForm(request.POST)
    if form.is_valid():
        u = Underline.objects.create(user=request.user, book=book,
            start=form.cleaned_data['start'],
            end=form.cleaned_data['end']
            )
        return HttpResponse(u.id)


@login_required
@require_POST
def comment(request, slug):
    book = get_object_or_404(Book, slug=slug)

    form = UnderlineCommentForm(request.POST)
    if form.is_valid():
        u = get_object_or_404(Underline, pk=form.cleaned_data['uid'],
                user=request.user)
        u.comment=form.cleaned_data['comment']
        u.save()
        return HttpResponse(u.id)


