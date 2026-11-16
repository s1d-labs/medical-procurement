import ssl

import taskrun


def test_expired_cert_hosts_keep_chain_and_hostname_checks():
    s = taskrun.session()
    adapter = s.get_adapter("https://www.wbmsc.gov.in/award-of-work.php")
    assert isinstance(adapter, taskrun.NoExpiryCheck)
    ctx = adapter.poolmanager.connection_pool_kw["ssl_context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert ctx.verify_flags & 0x200000
    # every other host keeps the default adapter (full verification)
    assert not isinstance(s.get_adapter("https://web.archive.org/"), taskrun.NoExpiryCheck)
