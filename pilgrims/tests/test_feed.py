from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .. import imaging
from ..models import Comment, Follow, PilgrimPhoto, Post, PostPhoto
from ..permissions import visible_posts_for
from .factories import make_uploaded_jpeg
from .test_photos import _make_site, _PrivateStorageTestCase


class PortalHomeRedirectTests(TestCase):
    """/pilgrims/ lands a signed-in pilgrim on the feed — matches the
    original phase-1 plan, which the profile-page redirect was always meant
    to be an interim stand-in for until the feed existed (phase 3)."""

    def test_authenticated_user_redirected_to_feed(self):
        user = User.objects.create_user("portal_home_user", "portal_home_user@example.com", "pw")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("pilgrims:home"))
        self.assertRedirects(response, reverse("pilgrims:feed"))

    def test_anonymous_user_sees_marketing_page(self):
        client = Client()
        response = client.get(reverse("pilgrims:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pilgrims/marketing.html")


class FeedQueryCountTests(_PrivateStorageTestCase):
    """The spec's explicit requirement: a 20-post feed with photos and
    comments must not scale its query count with the number of posts."""

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "pw")
        self.viewer = User.objects.create_user("viewer", "viewer@example.com", "pw")
        Follow.objects.create(follower=self.viewer, following=self.owner, status=Follow.STATUS_ACCEPTED)
        self.site = _make_site()

        for i in range(20):
            processed = imaging.process_upload(make_uploaded_jpeg(width=100 + i, height=100 + i))
            photo = PilgrimPhoto.create_from_processed(owner=self.owner, site=self.site, processed=processed)
            post = Post.objects.create(owner=self.owner, site=self.site, caption=f"Post {i}")
            PostPhoto.objects.create(post=post, photo=photo, sort_order=0)
            for j in range(2):
                Comment.objects.create(post=post, author=self.owner, body=f"comment {j}")

    def _render(self, limit):
        posts = list(visible_posts_for(self.viewer)[:limit])
        for post in posts:
            list(post.post_photos.all())
            list(post.preview_comments)
        return posts

    def test_feed_query_count_does_not_scale_with_post_count(self):
        # The real invariant: the SAME query count at two different N proves
        # this is O(1) in the number of posts, not just "small enough to
        # look flat at N=20". (The constant itself — a handful of queries to
        # resolve owner_ids, then one each for posts/post_photos/comments —
        # is an implementation detail not worth hardcoding here.)
        with CaptureQueriesContext(connection) as small:
            posts_5 = self._render(5)
        with CaptureQueriesContext(connection) as large:
            posts_20 = self._render(20)

        self.assertEqual(len(posts_5), 5)
        self.assertEqual(len(posts_20), 20)
        self.assertEqual(
            len(small.captured_queries), len(large.captured_queries),
            "query count scaled with the number of posts in the feed",
        )
        # And it should be small in absolute terms — a handful of fixed
        # setup queries plus one per prefetch, not dozens.
        self.assertLess(len(large.captured_queries), 10)


class FeedCursorPaginationTests(_PrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("cursorowner", "cursorowner@example.com", "pw")
        self.viewer = User.objects.create_user("cursorviewer", "cursorviewer@example.com", "pw")
        Follow.objects.create(follower=self.viewer, following=self.owner, status=Follow.STATUS_ACCEPTED)
        self.client = Client()
        self.client.force_login(self.viewer)
        for i in range(25):
            Post.objects.create(owner=self.owner, caption=f"post {i}")

    def test_two_pages_cover_all_posts_with_no_duplicates_or_gaps(self):
        from django.urls import reverse

        page_1 = self.client.get(reverse("pilgrims:feed"))
        posts_page_1 = list(page_1.context["posts"])
        self.assertEqual(len(posts_page_1), 20)
        cursor = page_1.context["next_cursor"]
        self.assertIsNotNone(cursor)

        page_2 = self.client.get(reverse("pilgrims:feed"), {"cursor": cursor})
        posts_page_2 = list(page_2.context["posts"])
        self.assertEqual(len(posts_page_2), 5)
        self.assertIsNone(page_2.context["next_cursor"])

        all_uuids = {p.uuid for p in posts_page_1} | {p.uuid for p in posts_page_2}
        self.assertEqual(len(all_uuids), 25, "pagination produced duplicates or dropped posts")

    def test_new_post_landing_between_page_fetches_does_not_duplicate_or_skip(self):
        # The whole point of cursor (vs. offset) pagination: a new row
        # arriving between two fetches must not shift what page 2 sees.
        from django.urls import reverse

        page_1 = self.client.get(reverse("pilgrims:feed"))
        cursor = page_1.context["next_cursor"]

        Post.objects.create(owner=self.owner, caption="brand new, arrived after page 1")

        page_2 = self.client.get(reverse("pilgrims:feed"), {"cursor": cursor})
        posts_page_2 = list(page_2.context["posts"])
        self.assertEqual(len(posts_page_2), 5)
        self.assertNotIn("brand new, arrived after page 1", [p.caption for p in posts_page_2])


class VisiblePostsForTests(_PrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "pw")
        self.follower = User.objects.create_user("follower", "follower@example.com", "pw")
        self.pending = User.objects.create_user("pending", "pending@example.com", "pw")
        self.stranger = User.objects.create_user("stranger", "stranger@example.com", "pw")
        Follow.objects.create(follower=self.follower, following=self.owner, status=Follow.STATUS_ACCEPTED)
        Follow.objects.create(follower=self.pending, following=self.owner, status=Follow.STATUS_PENDING)
        self.post = Post.objects.create(owner=self.owner, caption="Hello")

    def test_owner_sees_own_post(self):
        self.assertIn(self.post, visible_posts_for(self.owner))

    def test_accepted_follower_sees_post(self):
        self.assertIn(self.post, visible_posts_for(self.follower))

    def test_pending_follower_does_not_see_post(self):
        self.assertNotIn(self.post, visible_posts_for(self.pending))

    def test_stranger_does_not_see_post(self):
        self.assertNotIn(self.post, visible_posts_for(self.stranger))

    def test_blocked_follower_loses_access(self):
        from ..models import Block

        Block.objects.create(blocker=self.owner, blocked=self.follower)
        self.assertNotIn(self.post, visible_posts_for(self.follower))
