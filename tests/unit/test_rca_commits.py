"""Unit tests for commit attribution (I9)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, SourceType
from rca.commits import attribute_deployment, latest_deployment

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def deploy(service: str, deploy_id: str, sha: str, offset: float) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"d-{deploy_id}",
        event_time=BASE + timedelta(seconds=offset),
        ingestion_time=BASE + timedelta(seconds=offset),
        source_type=SourceType.DEPLOYMENT,
        event_type="DEPLOYMENT",
        service_name=service,
        deployment_id=deploy_id,
        attributes={"commit_sha": sha},
    )


def test_attributes_the_deploy_to_the_same_service_before_onset():
    deployments = [
        deploy("payment-service", "dep-1", "c0ffee", offset=-30),
        deploy("user-service", "dep-decoy", "decoy", offset=+5),
    ]

    match = attribute_deployment("payment-service", BASE, deployments, window_seconds=900)

    assert match is not None
    assert match.commit_sha == "c0ffee"


def test_ignores_deployments_to_other_services():
    deployments = [deploy("user-service", "dep-decoy", "decoy", offset=-5)]

    match = attribute_deployment("payment-service", BASE, deployments, window_seconds=900)

    assert match is None


def test_ignores_deployments_after_onset():
    deployments = [deploy("payment-service", "dep-late", "late", offset=+5)]

    assert attribute_deployment("payment-service", BASE, deployments) is None


def test_latest_deployment_is_trapped_by_the_decoy():
    deployments = [
        deploy("payment-service", "dep-real", "c0ffee", offset=-5),
        deploy("user-service", "dep-decoy", "decoy", offset=+15),
    ]

    match = latest_deployment(BASE, deployments, window_seconds=900)

    assert match is not None
    assert match.service == "user-service"
