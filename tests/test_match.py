from datetime import date

from src.transform.match import clean_zip, map_product, name_parts, parse_date


def test_zip_cleaning_keeps_leading_zeros():
    assert clean_zip("2134") == "02134"        # number saved without its leading zero
    assert clean_zip("19343-4631") == "19343"  # ZIP+4
    assert clean_zip("12345.0") == "12345"     # spreadsheet float
    assert clean_zip(None) is None


def test_three_date_formats():
    assert parse_date("2021-03-05") == date(2021, 3, 5)
    assert parse_date("03/05/2021") == date(2021, 3, 5)
    assert parse_date("Mar 5, 2021") == date(2021, 3, 5)
    assert parse_date("garbage") is None


def test_name_variants_agree():
    assert name_parts("Jon Smith") == name_parts("SMITH, JONATHAN") == ("smith", "j")


def test_product_names_map_to_cfpb():
    assert map_product("CC") == "Credit card"
    assert map_product("360 Checking") == "Checking or savings account"
    assert map_product("VEH LOAN") == "Vehicle loan or lease"
