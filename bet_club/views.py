from django.shortcuts import render

def horse_view(request):
    return render(request, "horse.html")