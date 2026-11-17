"""The simulation database guard: off by default, strict when the runner turns it on."""
import pytest

from outbound import simguard

ON = {"SIM_DB_GUARD": "1", "SIM_ALLOWED_HOSTS": "ep-a.c-15.us-east-1.aws.neon.tech", "SIM_DB_PREFIX": "sim_"}


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SIM_DB_GUARD", raising=False)
    simguard.check("postgres://u@prod.example.com/anything")


@pytest.mark.parametrize("url", ["postgres://u:p@ep-a.c-15.us-east-1.aws.neon.tech/neondb?sslmode=require",
                                 "postgres://u:p@ep-a.c-15.us-east-1.aws.neon.tech/sim_outbound",
                                 "postgres://postgres@127.0.0.1:54349/p3_outbound"])
def test_allows_simulation_databases(monkeypatch, url):
    for k, v in ON.items():
        monkeypatch.setenv(k, v)
    simguard.check(url)


@pytest.mark.parametrize("url", ["postgres://u:p@ep-b.c-15.us-east-1.aws.neon.tech/neondb",
                                 "postgres://u:p@ep-a.c-15.us-east-1.aws.neon.tech/production",
                                 "postgres://u@127.0.0.1:5432/customers"])
def test_refuses_anything_else(monkeypatch, url):
    for k, v in ON.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit):
        simguard.check(url)


@pytest.mark.parametrize("url", ["postgres://u@127.0.0.1/p3_x?host=prod.example.com", "postgres://u@127.0.0.1/p3_x?dbname=customers",
                                 "postgres://u@127.0.0.1/p3_x?options=-c%20x", "postgres://u@127.0.0.1/p3_x?hostaddr=10.1.2.3",
                                 "postgres://a@prod.example.com,x@127.0.0.1/p3_x", "postgres://u@127.0.0.1/crm", "postgres://u@127.0.0.1/testprod"])
def test_refuses_weird_urls(monkeypatch, url):
    for k, v in ON.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit):
        simguard.check(url)


def test_refuses_pg_environment_overrides(monkeypatch):
    for k, v in ON.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PGHOST", "prod.example.com")
    with pytest.raises(SystemExit):
        simguard.check("postgres://u@127.0.0.1/p3_x")
