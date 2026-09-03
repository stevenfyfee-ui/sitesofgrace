"""
All four rate limits (follow requests, photo uploads, posts, comments)
already count rows in the table the action itself writes to — Follow,
PilgrimPhoto, Post, Comment — filtered on the actor and a created_at
window. None of them ever used django.core.cache, so there was nothing to
convert off LocMemCache (which is per-process and would silently multiply
the effective limit by the gunicorn worker count). See the settings.CACHES
report for the full audit; this file is the coverage that was missing:
  - a cap-fires test for the follow-request limit (the only one that had
    none at all — photo/post/comment already had one each, elsewhere)
  - a scoping test per limit, proving the count only ever includes the
    acting user's own rows inside the window — not other users' rows, and
    not the acting user's own rows from outside the window.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from .. import imaging
from ..models import Comment, Follow, PilgrimPhoto, Post
from ..views import COMMENTS_PER_HOUR, FOLLOW_REQUESTS_PER_DAY, PHOTO_UPLOADS_PER_HOUR, POSTS_PER_HOUR
from .factories import make_uploaded_jpeg, verify_email
from .test_photos import _make_site, _PrivateStorageTestCase


def _backdate(queryset, when):
    queryset.update(created_at=when)


class FollowRateLimitTests(_PrivateStorageTestCase):
    def setUp(self):
        self.actor = User.objects.create_user("follow_actor", "follow_actor@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.actor)

    def _new_target(self, n):
        return User.objects.create_user(f"follow_target_{n}", f"follow_target_{n}@example.com", "pw")

    def test_cap_fires(self):
        for i in range(FOLLOW_REQUESTS_PER_DAY):
            Follow.objects.create(follower=self.actor, following=self._new_target(i))

        one_more = self._new_target("one_more")
        response = self.client.post(reverse("pilgrims:follow", args=[one_more.pk]), {"next": "/"})
        self.assertEqual(Follow.objects.filter(follower=self.actor, following=one_more).count(), 0)
        self.assertIn("rate_limited=1", response["Location"])

    def test_scoped_to_actor_and_24h_window(self):
        other_user = User.objects.create_user("follow_other", "follow_other@example.com", "pw")
        # Someone else's follow requests, far above the cap — must not
        # count against self.actor's limit.
        for i in range(FOLLOW_REQUESTS_PER_DAY * 2):
            Follow.objects.create(follower=other_user, following=self._new_target(f"other_{i}"))

        # self.actor's OWN requests, but from outside the 24h window —
        # must not count either.
        old_targets = [self._new_target(f"old_{i}") for i in range(FOLLOW_REQUESTS_PER_DAY - 1)]
        for target in old_targets:
            Follow.objects.create(follower=self.actor, following=target)
        _backdate(
            Follow.objects.filter(follower=self.actor, following__in=old_targets),
            timezone.now() - timedelta(hours=25),
        )

        # self.actor should still be able to send a fresh request — none of
        # the rows above should have counted.
        fresh_target = self._new_target("fresh")
        response = self.client.post(reverse("pilgrims:follow", args=[fresh_target.pk]), {"next": "/"})
        self.assertTrue(Follow.objects.filter(follower=self.actor, following=fresh_target).exists())
        self.assertNotIn("rate_limited=1", response["Location"])


class PhotoUploadRateLimitScopingTests(_PrivateStorageTestCase):
    # test_photos.py:PhotoUploadViewTests already proves the cap fires.

    def test_scoped_to_actor_and_1h_window(self):
        actor = User.objects.create_user("upload_actor", "upload_actor@example.com", "pw")
        other_user = User.objects.create_user("upload_other", "upload_other@example.com", "pw")
        site = _make_site(slug="rl-upload-site")

        for _ in range(PHOTO_UPLOADS_PER_HOUR * 2):
            processed = imaging.process_upload(make_uploaded_jpeg())
            PilgrimPhoto.create_from_processed(owner=other_user, site=site, processed=processed)

        old_photos = []
        for _ in range(PHOTO_UPLOADS_PER_HOUR - 1):
            processed = imaging.process_upload(make_uploaded_jpeg())
            old_photos.append(PilgrimPhoto.create_from_processed(owner=actor, site=site, processed=processed))
        _backdate(
            PilgrimPhoto.objects.filter(pk__in=[p.pk for p in old_photos]),
            timezone.now() - timedelta(hours=2),
        )

        client = Client()
        client.force_login(actor)
        # Distinct dimensions so its content hash can't collide with the
        # default-bytes photos created above — this test is about the rate
        # limit, not the (separate, time-unbounded) duplicate-content check.
        response = client.post(reverse("pilgrims:photo_upload"), {
            "site_id": site.pk, "photo": make_uploaded_jpeg(width=321, height=321),
        })
        self.assertTrue(response.json()["success"], response.json())


class PostRateLimitScopingTests(_PrivateStorageTestCase):
    # test_posts.py:RateLimitTests already proves the cap fires.

    def test_scoped_to_actor_and_1h_window(self):
        actor = User.objects.create_user("post_actor", "post_actor@example.com", "pw")
        other_user = User.objects.create_user("post_other", "post_other@example.com", "pw")
        site = _make_site(slug="rl-post-site")

        Post.objects.bulk_create([Post(owner=other_user) for _ in range(POSTS_PER_HOUR * 2)])

        old_posts = Post.objects.bulk_create([Post(owner=actor) for _ in range(POSTS_PER_HOUR - 1)])
        _backdate(
            Post.objects.filter(pk__in=[p.pk for p in old_posts]),
            timezone.now() - timedelta(hours=2),
        )

        processed = imaging.process_upload(make_uploaded_jpeg())
        photo = PilgrimPhoto.create_from_processed(owner=actor, site=site, processed=processed)

        client = Client()
        client.force_login(actor)
        response = client.post(reverse("pilgrims:post_compose"), {"photo_uuid": [str(photo.uuid)]})
        self.assertTrue(response.json()["success"])


class CommentRateLimitScopingTests(_PrivateStorageTestCase):
    # test_posts.py:RateLimitTests already proves the cap fires.

    def test_scoped_to_actor_and_1h_window(self):
        owner = User.objects.create_user("comment_post_owner", "comment_post_owner@example.com", "pw")
        actor = User.objects.create_user("comment_actor", "comment_actor@example.com", "pw")
        other_user = User.objects.create_user("comment_other", "comment_other@example.com", "pw")
        verify_email(actor)
        Follow.objects.create(follower=actor, following=owner, status=Follow.STATUS_ACCEPTED)
        post = Post.objects.create(owner=owner)

        Comment.objects.bulk_create(
            [Comment(post=post, author=other_user, body=f"other {i}") for i in range(COMMENTS_PER_HOUR * 2)]
        )

        old_comments = Comment.objects.bulk_create(
            [Comment(post=post, author=actor, body=f"old {i}") for i in range(COMMENTS_PER_HOUR - 1)]
        )
        _backdate(
            Comment.objects.filter(pk__in=[c.pk for c in old_comments]),
            timezone.now() - timedelta(hours=2),
        )

        client = Client()
        client.force_login(actor)
        response = client.post(
            reverse("pilgrims:comment_add", args=[post.uuid]), {"body": "fresh comment"}
        )
        self.assertTrue(response.json()["success"])
