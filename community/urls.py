from django.urls import path

from . import views

urlpatterns = [
    path("set/", views.set_journey_status, name="journey_set"),
]
