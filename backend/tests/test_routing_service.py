import pytest
from unittest.mock import MagicMock
from backend.services.routing_service import RoutingService


@pytest.fixture
def service():
    return RoutingService()


def make_mock_channel(id, name, language_code):
    ch = MagicMock()
    ch.id = id
    ch.channel_name = name
    ch.language_code = language_code
    ch.is_active = True
    return ch


class TestRouting:
    def test_routes_to_correct_channel(self, service):
        db = MagicMock()
        channels = [
            make_mock_channel(1, "Canal PT", "pt"),
            make_mock_channel(2, "Canal ES", "es"),
        ]
        db.query.return_value.filter.return_value.all.return_value = channels

        routed, unroutable = service.route_files(
            ["aula_pt.mp4"], ["C:/videos/aula_pt.mp4"], [1, 2], db
        )
        assert len(routed) == 1
        assert routed[0].channel_id == 1
        assert routed[0].detected_language == "pt"

    def test_unroutable_when_no_matching_channel(self, service):
        db = MagicMock()
        channels = [make_mock_channel(1, "Canal PT", "pt")]
        db.query.return_value.filter.return_value.all.return_value = channels

        routed, unroutable = service.route_files(
            ["video_de.mp4"], ["C:/videos/video_de.mp4"], [1], db
        )
        assert len(routed) == 0
        assert len(unroutable) == 1

    def test_multi_channel_same_language(self, service):
        db = MagicMock()
        channels = [
            make_mock_channel(1, "PT Channel 1", "pt"),
            make_mock_channel(2, "PT Channel 2", "pt"),
        ]
        db.query.return_value.filter.return_value.all.return_value = channels

        routed, unroutable = service.route_files(
            ["aula_pt.mp4"], ["C:/videos/aula_pt.mp4"], [1, 2], db
        )
        assert len(routed) == 2  # sent to both PT channels
