from django.urls import path

from . import views

app_name = "tours"

urlpatterns = [
    path("go/tour/<int:pk>/", views.go_tour, name="go"),
    path("tours/interest/", views.tour_interest, name="interest"),
]
