#include <stddef.h>
#include <stdio.h>
#include <windows.h>
#include <fwpmu.h>

#define REPORT_SIZE(key, type) \
    printf(key "=%llu\n", (unsigned long long)sizeof(type))
#define REPORT_OFFSET(key, type, field) \
    printf(key "=%llu\n", (unsigned long long)offsetof(type, field))

static void CALLBACK layout_probe_callback(
    void *context, const FWPM_NET_EVENT3 *event) {
    (void)context;
    (void)event;
}

static FWPM_NET_EVENT_CALLBACK2 layout_probe_callback_type =
    layout_probe_callback;

int main(void) {
    (void)layout_probe_callback_type;
    REPORT_SIZE("subscription.size", FWPM_NET_EVENT_SUBSCRIPTION0);
    REPORT_OFFSET("subscription.enum_template", FWPM_NET_EVENT_SUBSCRIPTION0,
                  enumTemplate);
    REPORT_OFFSET("subscription.flags", FWPM_NET_EVENT_SUBSCRIPTION0, flags);
    REPORT_OFFSET("subscription.session_key", FWPM_NET_EVENT_SUBSCRIPTION0,
                  sessionKey);

    REPORT_SIZE("header.size", FWPM_NET_EVENT_HEADER3);
    REPORT_OFFSET("header.flags", FWPM_NET_EVENT_HEADER3, flags);
    REPORT_OFFSET("header.ip_version", FWPM_NET_EVENT_HEADER3, ipVersion);
    REPORT_OFFSET("header.ip_protocol", FWPM_NET_EVENT_HEADER3, ipProtocol);
    REPORT_OFFSET("header.local_address", FWPM_NET_EVENT_HEADER3, localAddrV4);
    REPORT_OFFSET("header.remote_address", FWPM_NET_EVENT_HEADER3, remoteAddrV4);
    REPORT_OFFSET("header.local_port", FWPM_NET_EVENT_HEADER3, localPort);
    REPORT_OFFSET("header.remote_port", FWPM_NET_EVENT_HEADER3, remotePort);
    REPORT_OFFSET("header.scope_id", FWPM_NET_EVENT_HEADER3, scopeId);
    REPORT_OFFSET("header.app_id", FWPM_NET_EVENT_HEADER3, appId);
    REPORT_OFFSET("header.user_id", FWPM_NET_EVENT_HEADER3, userId);
    REPORT_OFFSET("header.address_family", FWPM_NET_EVENT_HEADER3, addressFamily);
    REPORT_OFFSET("header.package_sid", FWPM_NET_EVENT_HEADER3, packageSid);
    REPORT_OFFSET("header.enterprise_id", FWPM_NET_EVENT_HEADER3, enterpriseId);
    REPORT_OFFSET("header.policy_flags", FWPM_NET_EVENT_HEADER3, policyFlags);
    REPORT_OFFSET("header.effective_name", FWPM_NET_EVENT_HEADER3, effectiveName);

    REPORT_SIZE("event.size", FWPM_NET_EVENT3);
    REPORT_OFFSET("event.type", FWPM_NET_EVENT3, type);
    REPORT_OFFSET("event.capability_drop", FWPM_NET_EVENT3, capabilityDrop);
    REPORT_SIZE("capability_drop.size", FWPM_NET_EVENT_CAPABILITY_DROP0);
    REPORT_OFFSET("capability_drop.network_capability_id",
                  FWPM_NET_EVENT_CAPABILITY_DROP0, networkCapabilityId);
    REPORT_OFFSET("capability_drop.filter_id", FWPM_NET_EVENT_CAPABILITY_DROP0,
                  filterId);
    REPORT_OFFSET("capability_drop.is_loopback", FWPM_NET_EVENT_CAPABILITY_DROP0,
                  isLoopback);
    return 0;
}
