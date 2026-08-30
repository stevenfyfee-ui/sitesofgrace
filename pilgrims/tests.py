from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from .models import Block, Follow
from .permissions import (
    accepted_following_ids,
    can_interact,
    can_view_profile_detail,
    is_following,
)


class PermissionsTestCase(TestCase):
    """Exercises every helper against: self, accepted follower, pending
    follower, stranger, blocked, anonymous, staff — per the phase-1 spec."""

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "pw")
        self.stranger = User.objects.create_user("stranger", "stranger@example.com", "pw")
        self.pending_follower = User.objects.create_user("pending", "pending@example.com", "pw")
        self.accepted_follower = User.objects.create_user("accepted", "accepted@example.com", "pw")
        self.blocked_user = User.objects.create_user("blocked", "blocked@example.com", "pw")
        self.staff = User.objects.create_user("staff", "staff@example.com", "pw", is_staff=True)
        self.anonymous = AnonymousUser()

        Follow.objects.create(follower=self.pending_follower, following=self.owner, status=Follow.STATUS_PENDING)
        Follow.objects.create(follower=self.accepted_follower, following=self.owner, status=Follow.STATUS_ACCEPTED)
        Block.objects.create(blocker=self.owner, blocked=self.blocked_user)

    # --- is_following ---------------------------------------------------

    def test_is_following_self(self):
        self.assertFalse(is_following(self.owner, self.owner))

    def test_is_following_accepted(self):
        self.assertTrue(is_following(self.accepted_follower, self.owner))

    def test_is_following_pending(self):
        self.assertFalse(is_following(self.pending_follower, self.owner))

    def test_is_following_stranger(self):
        self.assertFalse(is_following(self.stranger, self.owner))

    def test_is_following_blocked(self):
        self.assertFalse(is_following(self.blocked_user, self.owner))

    def test_is_following_anonymous(self):
        self.assertFalse(is_following(self.anonymous, self.owner))

    def test_is_following_staff(self):
        self.assertFalse(is_following(self.staff, self.owner))

    # --- can_view_profile_detail (owner.pilgrim.is_private defaults True) -

    def test_can_view_self(self):
        self.assertTrue(can_view_profile_detail(self.owner, self.owner))

    def test_can_view_accepted_follower(self):
        self.assertTrue(can_view_profile_detail(self.accepted_follower, self.owner))

    def test_can_view_pending_follower_denied(self):
        self.assertFalse(can_view_profile_detail(self.pending_follower, self.owner))

    def test_can_view_stranger_denied(self):
        self.assertFalse(can_view_profile_detail(self.stranger, self.owner))

    def test_can_view_blocked_denied(self):
        self.assertFalse(can_view_profile_detail(self.blocked_user, self.owner))

    def test_can_view_anonymous_denied_when_private(self):
        self.assertFalse(can_view_profile_detail(self.anonymous, self.owner))

    def test_can_view_anonymous_allowed_when_public(self):
        self.owner.pilgrim.is_private = False
        self.owner.pilgrim.save(update_fields=["is_private"])
        self.assertTrue(can_view_profile_detail(self.anonymous, self.owner))

    def test_can_view_staff_no_bypass(self):
        # No special-cased staff access to private profiles: SOC 2 access
        # discipline says a staff member sees a private profile the same
        # way a stranger does, not silently.
        self.assertFalse(can_view_profile_detail(self.staff, self.owner))

    # --- can_interact -----------------------------------------------------

    def test_can_interact_self(self):
        self.assertTrue(can_interact(self.owner, self.owner))

    def test_can_interact_accepted_follower(self):
        self.assertTrue(can_interact(self.accepted_follower, self.owner))

    def test_can_interact_pending_follower(self):
        self.assertTrue(can_interact(self.pending_follower, self.owner))

    def test_can_interact_stranger(self):
        self.assertTrue(can_interact(self.stranger, self.owner))

    def test_can_interact_blocked_either_direction(self):
        self.assertFalse(can_interact(self.blocked_user, self.owner))
        self.assertFalse(can_interact(self.owner, self.blocked_user))

    def test_can_interact_anonymous(self):
        self.assertTrue(can_interact(self.anonymous, self.owner))

    def test_can_interact_staff_no_bypass(self):
        Block.objects.create(blocker=self.staff, blocked=self.owner)
        self.assertFalse(can_interact(self.staff, self.owner))

    # --- accepted_following_ids --------------------------------------------

    def test_accepted_following_ids(self):
        ids = set(accepted_following_ids(self.accepted_follower))
        self.assertEqual(ids, {self.owner.pk})

    def test_accepted_following_ids_excludes_pending(self):
        self.assertEqual(set(accepted_following_ids(self.pending_follower)), set())

    def test_accepted_following_ids_stranger_empty(self):
        self.assertEqual(set(accepted_following_ids(self.stranger)), set())
