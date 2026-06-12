from sqlalchemy.orm import Session

from backend.models.channel import Channel
from backend.services.language_service import language_service
from backend.schemas.upload import RoutingEntry


class RoutingService:
    def route_files(
        self,
        file_names: list[str],
        file_paths: list[str],
        selected_channel_ids: list[int],
        db: Session,
    ) -> tuple[list[RoutingEntry], list[RoutingEntry]]:
        """
        Route files to channels based on detected language.
        Returns (routed, unroutable).
        """
        # Get selected channels
        channels = db.query(Channel).filter(
            Channel.id.in_(selected_channel_ids),
            Channel.is_active == True,
        ).all()

        # Build language->channels map
        lang_to_channels: dict[str, list[Channel]] = {}
        for ch in channels:
            if ch.language_code:
                lang_to_channels.setdefault(ch.language_code, []).append(ch)

        routed: list[RoutingEntry] = []
        unroutable: list[RoutingEntry] = []

        for name, path in zip(file_names, file_paths):
            lang_code, method = language_service.detect_language(name)

            if lang_code and lang_code in lang_to_channels:
                # Route to all matching channels
                for ch in lang_to_channels[lang_code]:
                    routed.append(RoutingEntry(
                        file_name=name,
                        file_path=path,
                        detected_language=lang_code,
                        detection_method=method,
                        channel_id=ch.id,
                        channel_name=ch.channel_name,
                    ))
            else:
                unroutable.append(RoutingEntry(
                    file_name=name,
                    file_path=path,
                    detected_language=lang_code,
                    detection_method=method,
                    channel_id=None,
                    channel_name=None,
                ))

        return routed, unroutable


routing_service = RoutingService()
