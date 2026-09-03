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

    path("photos/sites/search/", views.photo_site_search, name="photo_site_search"),
    path("photos/upload/", views.photo_upload, name="photo_upload"),
    path("my/photos/", views.photo_library, name="photo_library"),
    path("my/photos/<slug:site_slug>/", views.photo_album, name="photo_album"),
    path("photos/<uuid:photo_uuid>/", views.photo_detail, name="photo_detail"),
    path("photos/<uuid:photo_uuid>/delete/", views.photo_delete, name="photo_delete"),
    path("photos/<uuid:photo_uuid>/caption/", views.photo_caption_edit, name="photo_caption_edit"),
    path("photos/bulk-delete/", views.photo_bulk_delete, name="photo_bulk_delete"),

    path("feed/", views.feed, name="feed"),
    path("posts/new/", views.post_compose, name="post_compose"),
    path("posts/photos-for-site/", views.compose_photos_for_site, name="compose_photos_for_site"),
    path("posts/<uuid:post_uuid>/", views.post_detail, name="post_detail"),
    path("posts/<uuid:post_uuid>/delete/", views.post_delete, name="post_delete"),
    path("posts/<uuid:post_uuid>/comments/", views.comment_add, name="comment_add"),
    path("comments/<uuid:comment_uuid>/delete/", views.comment_delete, name="comment_delete"),

    path("notifications/", views.notifications_list, name="notifications"),

    path("photos/<uuid:photo_uuid>/share/", views.photo_share, name="photo_share"),
    path("photos/<uuid:photo_uuid>/unshare/", views.photo_unshare, name="photo_unshare"),
    path("photos/<uuid:photo_uuid>/report/", views.report_photo, name="report_photo"),
]
