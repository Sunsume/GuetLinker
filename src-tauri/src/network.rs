use std::net::{IpAddr, Ipv6Addr};

pub fn select_preferred_ipv6<I>(candidates: I) -> String
where
    I: IntoIterator<Item = (String, bool, bool)>,
{
    candidates
        .into_iter()
        .filter_map(|(address, same_interface, dns_eligible)| {
            let normalized = address.split('%').next().unwrap_or_default();
            let parsed = normalized.parse::<Ipv6Addr>().ok()?;
            is_global_ipv6(parsed).then(|| {
                let score = u8::from(same_interface) * 2 + u8::from(dns_eligible);
                (score, normalized.to_owned())
            })
        })
        .max_by_key(|(score, _)| *score)
        .map(|(_, address)| address)
        .unwrap_or_default()
}

#[cfg(windows)]
pub fn find_local_ipv6(ipv4_hint: &str) -> String {
    let candidates = ipconfig::get_adapters()
        .unwrap_or_default()
        .into_iter()
        .flat_map(|adapter| {
            let same_interface = !ipv4_hint.is_empty()
                && adapter
                    .ip_addresses()
                    .iter()
                    .any(|address| address.to_string() == ipv4_hint);
            let dns_eligible = !adapter.dns_servers().is_empty();
            adapter
                .ip_addresses()
                .iter()
                .filter_map(|address| match address {
                    IpAddr::V6(ipv6) => Some((ipv6.to_string(), same_interface, dns_eligible)),
                    IpAddr::V4(_) => None,
                })
                .collect::<Vec<_>>()
        });
    select_preferred_ipv6(candidates)
}

#[cfg(not(windows))]
pub fn find_local_ipv6(_ipv4_hint: &str) -> String {
    String::new()
}

fn is_global_ipv6(address: Ipv6Addr) -> bool {
    let first = address.octets()[0];
    !address.is_unspecified()
        && !address.is_loopback()
        && !address.is_multicast()
        && !address.is_unicast_link_local()
        && first & 0xfe != 0xfc
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prefers_matching_interface_and_dns_eligibility() {
        let selected = select_preferred_ipv6([
            ("fe80::1".into(), true, true),
            ("2606:4700:4700::1001".into(), false, true),
            ("2606:4700:4700::1001".into(), true, false),
            ("2606:4700:4700::1111".into(), true, true),
        ]);
        assert_eq!(selected, "2606:4700:4700::1111");
    }
}
