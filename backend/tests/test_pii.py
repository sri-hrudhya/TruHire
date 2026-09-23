from backend.services.pii import redact_pii, detect_pii


def test_pii_detection():
    sample_text = (
        "Contact John at john.doe@cyberdyne.org or call 415-555-0199. "
        "SSN is 000-12-3456 and address is 100 Main Street."
    )
    detected = detect_pii(sample_text)
    assert len(detected["emails"]) == 1
    assert "john.doe@cyberdyne.org" in detected["emails"]
    assert len(detected["phones"]) >= 1
    assert len(detected["ssn"]) == 1
    assert len(detected["addresses"]) == 1


def test_pii_redaction_email_phone_address_ssn():
    raw_resume = (
        "Alice Smith\n"
        "Email: alice.smith@google.com\n"
        "Phone: (555) 234-5678\n"
        "Address: 742 Evergreen Terrace\n"
        "SSN: 123-45-6789\n"
        "Senior Software Engineer with 7 years of Python and React experience."
    )
    redacted = redact_pii(raw_resume, candidate_name="Alice Smith")

    assert "alice.smith@google.com" not in redacted
    assert "[EMAIL]" in redacted

    assert "(555) 234-5678" not in redacted
    assert "[PHONE]" in redacted

    assert "123-45-6789" not in redacted
    assert "[ID]" in redacted

    assert "742 Evergreen Terrace" not in redacted
    assert "[ADDRESS]" in redacted

    assert "Alice Smith" not in redacted
    assert "[NAME]" in redacted

    # Non-PII professional content remains intact
    assert "Python" in redacted
    assert "React" in redacted
