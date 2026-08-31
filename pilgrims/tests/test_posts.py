from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from .. import imaging
from ..models import Comment, Follow, Notification, PilgrimPhoto, Post, PostPhoto
from .factories import make_uploaded_jpeg, verify_email
from .test_photos import _make_site, _PrivateStorageTestCase


def _make_photo(owner, site):
    processed = imaging.process_upload(make_uploaded_jpeg())
    return PilgrimPhoto.create_from_processed(owner=owner, site=site, processed=processed)


class ThreeAccountWalkthroughTests(_PrivateStorageTestCase):
    """Mirrors the phase-3 finish-step QA script: A posts, B (accepted
    follower) sees/comments, C (stranger) is shut out everywhere, A deletes
    B's comment, A blocks B and B immediately loses access."""

    def setUp(self):
        self.a = User.objects.create_user("alice", "alice@example.com", "pw")
        self.b = User.objects.create_user("bob", "bob@example.com", "pw")
        self.c = User.objects.create_user("carol", "carol@example.com", "pw")
        verify_email(self.b)
        verify_email(self.c)
        Follow.objects.create(follower=self.b, following=self.a, status=Follow.STATUS_ACCEPTED)
        self.site = _make_site()
        self.photo = _make_photo(self.a, self.site)

        self.client_a = Client()
        self.client_a.force_login(self.a)
        self.client_b = Client()
        self.client_b.force_login(self.b)
        self.client_c = Client()
        self.client_c.force_login(self.c)

        response = self.client_a.post(reverse("pilgrims:post_compose"), {
            "photo_uuid": [str(self.photo.uuid)],
            "caption": "At the shrine today.",
        })
        self.post_uuid = response.json()["post_uuid"]
        self.post = Post.objects.get(uuid=self.post_uuid)

    def test_bob_sees_post_in_feed(self):
        response = self.client_b.get(reverse("pilgrims:feed"))
        self.assertContains(response, "At the shrine today.")

    def test_carol_does_not_see_post_in_feed(self):
        response = self.client_c.get(reverse("pilgrims:feed"))
        self.assertNotContains(response, "At the shrine today.")

    def test_carol_gets_404_on_permalink(self):
        response = self.client_c.get(reverse("pilgrims:post_detail", args=[self.post_uuid]))
        self.assertEqual(response.status_code, 404)

    def test_carol_cannot_comment_via_crafted_post(self):
        response = self.client_c.post(
            reverse("pilgrims:comment_add", args=[self.post_uuid]), {"body": "sneaky"}
        )
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(Comment.objects.filter(post=self.post).count(), 0)

    def test_bob_comments_on_post_and_on_photo(self):
        r1 = self.client_b.post(
            reverse("pilgrims:comment_add", args=[self.post_uuid]), {"body": "Beautiful place"}
        )
        self.assertTrue(r1.json()["success"])
        r2 = self.client_b.post(
            reverse("pilgrims:comment_add", args=[self.post_uuid]),
            {"body": "Lovely light here", "photo_uuid": str(self.photo.uuid)},
        )
        self.assertTrue(r2.json()["success"])

        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 2)
        self.assertEqual(
            Comment.objects.filter(post=self.post, photo__isnull=True).count(), 1
        )
        self.assertEqual(
            Comment.objects.filter(post=self.post, photo=self.photo).count(), 1
        )
        # Alice (post owner) got notified twice.
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.a, actor=self.b, verb=Notification.VERB_COMMENT_ON_POST
            ).count(),
            2,
        )

    def test_alice_deletes_bobs_comment(self):
        self.client_b.post(reverse("pilgrims:comment_add", args=[self.post_uuid]), {"body": "hi"})
        comment = Comment.objects.get(post=self.post, author=self.b)
        response = self.client_a.post(reverse("pilgrims:comment_delete", args=[comment.uuid]))
        self.assertTrue(response.json()["success"])
        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 0)

    def test_stranger_cannot_delete_others_comment(self):
        self.client_b.post(reverse("pilgrims:comment_add", args=[self.post_uuid]), {"body": "hi"})
        comment = Comment.objects.get(post=self.post, author=self.b)
        response = self.client_c.post(reverse("pilgrims:comment_delete", args=[comment.uuid]))
        self.assertEqual(response.status_code, 404)
        comment.refresh_from_db()
        self.assertFalse(comment.is_deleted)

    def test_alice_blocks_bob_and_bob_immediately_loses_access(self):
        # Confirm access first.
        self.assertEqual(
            self.client_b.get(reverse("pilgrims:post_detail", args=[self.post_uuid])).status_code, 200
        )
        self.client_a.post(reverse("pilgrims:block", args=[self.b.pk]), {"next": "/"})

        response = self.client_b.get(reverse("pilgrims:post_detail", args=[self.post_uuid]))
        self.assertEqual(response.status_code, 404)
        feed_response = self.client_b.get(reverse("pilgrims:feed"))
        self.assertNotContains(feed_response, "At the shrine today.")


class ReplyDepthTests(_PrivateStorageTestCase):
    def setUp(self):
        self.a = User.objects.create_user("alice2", "alice2@example.com", "pw")
        self.b = User.objects.create_user("bob2", "bob2@example.com", "pw")
        verify_email(self.b)
        Follow.objects.create(follower=self.b, following=self.a, status=Follow.STATUS_ACCEPTED)
        self.post = Post.objects.create(owner=self.a, caption="Reflections")
        self.client_b = Client()
        self.client_b.force_login(self.b)

    def test_reply_to_reply_is_rejected(self):
        top = Comment.objects.create(post=self.post, author=self.a, body="top")
        reply = Comment.objects.create(post=self.post, author=self.b, parent=top, body="reply")
        response = self.client_b.post(
            reverse("pilgrims:comment_add", args=[self.post.uuid]),
            {"body": "reply to a reply", "parent_uuid": str(reply.uuid)},
        )
        data = response.json()
        self.assertFalse(data["success"])
        self.assertFalse(Comment.objects.filter(body="reply to a reply").exists())

    def test_reply_to_top_level_notifies_parent_author(self):
        top = Comment.objects.create(post=self.post, author=self.a, body="top")
        response = self.client_b.post(
            reverse("pilgrims:comment_add", args=[self.post.uuid]),
            {"body": "a reply", "parent_uuid": str(top.uuid)},
        )
        self.assertTrue(response.json()["success"])
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.a, actor=self.b, verb=Notification.VERB_COMMENT_REPLY
            ).exists()
        )


class RateLimitTests(_PrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("limited", "limited@example.com", "pw")
        self.owner = User.objects.create_user("owner3", "owner3@example.com", "pw")
        verify_email(self.user)
        Follow.objects.create(follower=self.user, following=self.owner, status=Follow.STATUS_ACCEPTED)
        self.post = Post.objects.create(owner=self.owner, caption="x")
        self.client = Client()
        self.client.force_login(self.user)

    def test_comment_rate_limit_is_friendly_not_500(self):
        from datetime import timedelta

        from django.utils import timezone

        from ..views import COMMENTS_PER_HOUR

        for i in range(COMMENTS_PER_HOUR):
            Comment.objects.create(post=self.post, author=self.user, body=f"c{i}")

        response = self.client.post(
            reverse("pilgrims:comment_add", args=[self.post.uuid]), {"body": "one too many"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "rate_limited")

    def test_post_rate_limit_is_friendly_not_500(self):
        from ..views import POSTS_PER_HOUR

        for i in range(POSTS_PER_HOUR):
            Post.objects.create(owner=self.user, caption=f"post {i}")

        site = _make_site(slug=f"rl-site")
        photo = _make_photo(self.user, site)
        response = self.client.post(reverse("pilgrims:post_compose"), {"photo_uuid": [str(photo.uuid)]})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "rate_limited")


class UnverifiedEmailCannotCommentTests(_PrivateStorageTestCase):
    def test_accepted_follower_without_verified_email_cannot_comment(self):
        owner = User.objects.create_user("owner5", "owner5@example.com", "pw")
        follower = User.objects.create_user("follower5", "follower5@example.com", "pw")
        # Deliberately NOT calling verify_email() here.
        Follow.objects.create(follower=follower, following=owner, status=Follow.STATUS_ACCEPTED)
        post = Post.objects.create(owner=owner, caption="x")

        client = Client()
        client.force_login(follower)
        response = client.post(reverse("pilgrims:comment_add", args=[post.uuid]), {"body": "hi"})
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(Comment.objects.filter(post=post).count(), 0)


class PhotoCountSyncTests(_PrivateStorageTestCase):
    def test_deleting_a_photo_decrements_post_photo_count(self):
        owner = User.objects.create_user("owner6", "owner6@example.com", "pw")
        site = _make_site()
        photo_1 = _make_photo(owner, site)
        photo_2 = _make_photo(owner, site)
        post = Post.objects.create(owner=owner, photo_count=2)
        PostPhoto.objects.create(post=post, photo=photo_1, sort_order=0)
        PostPhoto.objects.create(post=post, photo=photo_2, sort_order=1)

        photo_1.delete()  # phase-2 delete path, not through any phase-3 view

        post.refresh_from_db()
        self.assertEqual(post.photo_count, 1)
        self.assertEqual(post.post_photos.count(), 1)


class PostPhotoCleanTests(_PrivateStorageTestCase):
    def test_post_photo_rejects_mismatched_owner(self):
        from django.core.exceptions import ValidationError

        owner = User.objects.create_user("owner4", "owner4@example.com", "pw")
        other = User.objects.create_user("other4", "other4@example.com", "pw")
        site = _make_site()
        photo = _make_photo(other, site)
        post = Post.objects.create(owner=owner)
        pp = PostPhoto(post=post, photo=photo)
        with self.assertRaises(ValidationError):
            pp.clean()
