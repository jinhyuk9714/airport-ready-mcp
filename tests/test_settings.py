from departure_ready.settings import Settings


def test_supported_airport_list_parses_csv():
    settings = Settings(supported_airports="ICN,GMP,CJU")
    assert settings.supported_airport_list == ["ICN", "GMP", "CJU"]
