"""Tests for API endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models import JobMode, JobStatus


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "mock_render" in data
        assert "mock_script" in data


class TestJobEndpoints:
    """Tests for job CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_job(self, client: AsyncClient, sample_briefing: str):
        response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["telegram_user_id"] == 12345
        assert data["briefing"] == sample_briefing
        assert data["status"] == JobStatus.BRIEFING_RECEIVED.value

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient):
        response = await client.get("/api/v1/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_jobs_with_data(self, client: AsyncClient, sample_briefing: str):
        # Create a job first
        await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )

        response = await client.get("/api/v1/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_user(self, client: AsyncClient, sample_briefing: str):
        # Create jobs for different users
        await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 11111,
                "telegram_chat_id": 11111,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 22222,
                "telegram_chat_id": 22222,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )

        response = await client.get("/api/v1/jobs", params={"user_id": 11111})

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["telegram_user_id"] == 11111

    @pytest.mark.asyncio
    async def test_get_job_by_id(self, client: AsyncClient, sample_briefing: str):
        # Create a job
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]

        response = await client.get(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_job_by_prefix(self, client: AsyncClient, sample_briefing: str):
        # Create a job
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]
        prefix = job_id[:8]

        response = await client.get(f"/api/v1/jobs/{prefix}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient):
        response = await client.get("/api/v1/jobs/nonexistent-id")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job(self, client: AsyncClient, sample_briefing: str):
        # Create a job
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]

        response = await client.delete(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 204

        # Verify job is cancelled
        get_response = await client.get(f"/api/v1/jobs/{job_id}")
        assert get_response.json()["status"] == JobStatus.CANCELLED.value


class TestScriptEndpoints:
    """Tests for script-related endpoints."""

    @pytest.mark.asyncio
    async def test_generate_script(self, client: AsyncClient, sample_briefing: str):
        # Create a job
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]

        response = await client.post(f"/api/v1/jobs/{job_id}/script/generate")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == JobStatus.SCRIPT_PENDING_REVIEW.value
        assert len(data["scenes"]) > 0
        assert data["title"] is not None

    @pytest.mark.asyncio
    async def test_approve_script(self, client: AsyncClient, sample_briefing: str):
        # Create and generate script
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]
        await client.post(f"/api/v1/jobs/{job_id}/script/generate")

        response = await client.post(f"/api/v1/jobs/{job_id}/script/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == JobStatus.SCRIPT_APPROVED.value

    @pytest.mark.asyncio
    async def test_approve_script_wrong_status(self, client: AsyncClient, sample_briefing: str):
        # Create a job without generating script
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]

        response = await client.post(f"/api/v1/jobs/{job_id}/script/approve")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_regenerate_script(self, client: AsyncClient, sample_briefing: str):
        # Create and generate script
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]
        await client.post(f"/api/v1/jobs/{job_id}/script/generate")

        response = await client.post(f"/api/v1/jobs/{job_id}/script/regenerate")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == JobStatus.SCRIPT_PENDING_REVIEW.value


class TestRenderQueueEndpoints:
    """Tests for render queue endpoints."""

    @pytest.mark.asyncio
    async def test_get_next_render_task_empty(self, client: AsyncClient):
        response = await client.get("/api/v1/render-queue/next")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_get_next_render_task_with_job(self, client: AsyncClient, sample_briefing: str):
        # Create job and approve script
        create_response = await client.post(
            "/api/v1/jobs",
            json={
                "telegram_user_id": 12345,
                "telegram_chat_id": 12345,
                "briefing": sample_briefing,
                "mode": "brief",
            },
        )
        job_id = create_response.json()["id"]
        await client.post(f"/api/v1/jobs/{job_id}/script/generate")
        await client.post(f"/api/v1/jobs/{job_id}/script/approve")

        response = await client.get("/api/v1/render-queue/next")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "scene_order" in data
        assert "task_type" in data
