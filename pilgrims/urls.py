from django.urls import path

from . import views

app_name = "pilgrims"

urlpatterns = [
    path("", views.portal_home, name="home"),
    path("u/<slug:handle>/", views.profile_detail, name="profile_detail"),
    path("settings/", views.profile_settings, name="settings"),
    path("requests/", views.follow_requests, name="requests"),
    path("following/", views.following_list, name="following"),
    path("followers/", views.followers_list, name="followers"),

    path("follow/<int:user_id>/", views.follow_user, name="follow"),
    path("unfollow/<int:user_id>/", views.unfollow_user, name="unfollow"),
    path("approve/<int:follow_id>/", views.approve_request, name="approve"),
    path("decline/<int:follow_id>/", views.decline_request, name="decline"),
    path("remove-follower/<int:user_id>/", views.remove_follower, name="remove_follower"),
    path("block/<int:user_id>/", views.block_user, name="block"),
    path("unblock/<int:user_id>/", views.unblock_user, name="unblock"),
]
