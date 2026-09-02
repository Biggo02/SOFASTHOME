from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Property
from .search_views import matching_score


class MatchingScoreTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='matching-owner', password='test-pass')
        self.property = Property.objects.create(
            owner=self.owner,
            title='Maison test',
            property_type='Maison',
            province='Haut-Katanga',
            city='Lubumbashi',
            commune='Annexe',
            bedrooms=3,
            salons=2,
            max_occupants=6,
            rent=Decimal('500000'),
            status='published',
        )

    def test_all_exact_criteria_can_reach_100(self):
        criteria = {
            'province': 'Haut-Katanga', 'city': 'Lubumbashi', 'commune': 'Annexe',
            'salons': 2, 'bedrooms': 3, 'max_occupants': 6, 'rent': Decimal('500000'),
        }
        score, _ = matching_score(self.property, criteria)
        self.assertEqual(score, 100)

    def test_numeric_shortfall_is_progressive(self):
        criteria = {
            'province': '', 'city': '', 'commune': '',
            'salons': 4, 'bedrooms': 4, 'max_occupants': 8, 'rent': Decimal('500000'),
        }
        score, _ = matching_score(self.property, criteria)
        self.assertEqual(score, 78)

    def test_zero_rent_never_gets_budget_points(self):
        self.property.rent = Decimal('0')
        self.property.save(update_fields=['rent'])
        criteria = {
            'province': 'Haut-Katanga', 'city': 'Lubumbashi', 'commune': 'Annexe',
            'salons': 2, 'bedrooms': 3, 'max_occupants': 6, 'rent': Decimal('500000'),
        }
        score, breakdown = matching_score(self.property, criteria)
        self.assertLess(score, 100)
        self.assertEqual(next(item['earned'] for item in breakdown if item['label'] == 'Loyer mensuel'), 0)
