"""Unit tests for JobsUzScraperAdapter."""
from uzmyjob.adapters.jobs_uz import JobsUzScraperAdapter


def test_jobs_uz_normalize():
    """jobs.uz e'lonini to'g'ri normallashtirish."""
    adapter = JobsUzScraperAdapter()
    raw = {
        "id": "778899",
        "url": "https://jobs.uz/ru/vacancies/view/778899",
        "title": "Django Backend Muhandis",
        "company": "IT Hub",
        "city": "Samarqand",
        "salary_min": 1500,
        "salary_max": 2500,
        "currency": "USD",
        "email": "jobs@ithub.uz",
    }

    norm = adapter.normalize(raw)
    assert norm["source"] == "jobs_uz"
    assert norm["external_id"] == "778899"
    assert norm["title"] == "Django Backend Muhandis"
    assert norm["city"] == "Samarqand"
    assert norm["salary_min"] == 1500
    assert norm["currency"] == "USD"
    assert norm["contact_email"] == "jobs@ithub.uz"
