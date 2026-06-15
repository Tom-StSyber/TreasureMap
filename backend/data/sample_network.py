"""
TreasureMap — Sample lab network topology.

Topology:
  internet (cloud)
       |
  fw-01 (Cisco ASA — firewall)  ←── has_firewall=True on WAN link
       |
  router-core-01 (Cisco ASR) ──────── router-core-02 (Juniper MX, disabled link)
       |                  \\
  sw-dist-01              sw-dist-02
  (Extreme)               (Cisco Cat, trunk)
    |    \\                    |
 sw-acc-01  sw-acc-02      sw-acc-03
 (Cisco)    (Cisco)        (Nokia)
    |             |              |
 server-01     server-02     jumpbox-01
 (Linux)       (Linux)       (Windows)
"""
from models import Device, Interface, Connection, Acl, AclRule
import uuid

# ─────────────────────────────────────────────────────────────────
# Helper to make IDs deterministic (easier to cross-reference)
# ─────────────────────────────────────────────────────────────────
def _id(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"treasuremap.{seed}"))


# ─────────────────────────────────────────────────────────────────
# DEVICES
# ─────────────────────────────────────────────────────────────────
DEVICES: list[Device] = [
    Device(
        id=_id("internet"), name="internet", hostname="internet",
        management_ip="0.0.0.0", vendor="N/A", model="Cloud",
        os="N/A", device_type="cloud", location="WAN",
        tags=["internet", "external"],
    ),
    Device(
        id=_id("fw-01"), name="fw-01", hostname="fw-01.lab.local",
        management_ip="10.0.0.1", vendor="Cisco", model="ASA 5525-X",
        os="ASA-OS", device_type="firewall", location="DC-Rack-A1",
        tags=["firewall", "perimeter"],
    ),
    Device(
        id=_id("router-core-01"), name="router-core-01", hostname="router-core-01.lab.local",
        management_ip="10.0.1.1", vendor="Cisco", model="ASR 1001-X",
        os="IOS-XE", device_type="router", location="DC-Rack-A2",
        tags=["core", "router"],
    ),
    Device(
        id=_id("router-core-02"), name="router-core-02", hostname="router-core-02.lab.local",
        management_ip="10.0.1.2", vendor="Juniper", model="MX240",
        os="JunOS", device_type="router", location="DC-Rack-A3",
        tags=["core", "router", "backup"],
    ),
    Device(
        id=_id("sw-dist-01"), name="sw-dist-01", hostname="sw-dist-01.lab.local",
        management_ip="10.0.2.1", vendor="Extreme", model="X670-G2-48x",
        os="ExtremeXOS", device_type="switch", location="DC-Rack-B1",
        tags=["distribution", "switch"],
    ),
    Device(
        id=_id("sw-dist-02"), name="sw-dist-02", hostname="sw-dist-02.lab.local",
        management_ip="10.0.2.2", vendor="Cisco", model="Catalyst 9300",
        os="IOS-XE", device_type="switch", location="DC-Rack-B2",
        tags=["distribution", "switch"],
    ),
    Device(
        id=_id("sw-acc-01"), name="sw-acc-01", hostname="sw-acc-01.lab.local",
        management_ip="10.0.3.1", vendor="Cisco", model="Catalyst 2960X",
        os="IOS", device_type="switch", location="DC-Rack-C1",
        tags=["access", "switch"],
    ),
    Device(
        id=_id("sw-acc-02"), name="sw-acc-02", hostname="sw-acc-02.lab.local",
        management_ip="10.0.3.2", vendor="Cisco", model="Catalyst 2960X",
        os="IOS", device_type="switch", location="DC-Rack-C2",
        tags=["access", "switch"],
    ),
    Device(
        id=_id("sw-acc-03"), name="sw-acc-03", hostname="sw-acc-03.lab.local",
        management_ip="10.0.3.3", vendor="Nokia", model="7210 SAS-K",
        os="SR-OS", device_type="switch", location="DC-Rack-C3",
        tags=["access", "switch"],
    ),
    Device(
        id=_id("server-01"), name="server-01", hostname="server-01.lab.local",
        management_ip="10.10.10.101", vendor="Dell", model="PowerEdge R750",
        os="Ubuntu 22.04", device_type="server", location="DC-Rack-D1",
        tags=["server", "linux"],
    ),
    Device(
        id=_id("server-02"), name="server-02", hostname="server-02.lab.local",
        management_ip="10.10.20.101", vendor="HP", model="ProLiant DL380",
        os="RHEL 9", device_type="server", location="DC-Rack-D2",
        tags=["server", "linux"],
    ),
    Device(
        id=_id("jumpbox-01"), name="jumpbox-01", hostname="jumpbox-01.lab.local",
        management_ip="10.10.30.10", vendor="Dell", model="OptiPlex 7090",
        os="Windows Server 2022", device_type="server", location="DC-Rack-D3",
        tags=["jumpbox", "windows", "management"],
    ),
]

# Quick lookup
_dev = {d.name: d for d in DEVICES}


# ─────────────────────────────────────────────────────────────────
# INTERFACES
# ─────────────────────────────────────────────────────────────────
INTERFACES: list[Interface] = [
    # ── internet pseudo-node ──
    Interface(id=_id("internet.wan0"), device_id=_id("internet"), device_name="internet",
              name="wan0", description="WAN upstream", ip_address="203.0.113.1",
              prefix_length=30, admin_status="up", oper_status="up"),

    # ── fw-01 ──
    Interface(id=_id("fw-01.outside"), device_id=_id("fw-01"), device_name="fw-01",
              name="GigabitEthernet0/0", description="Outside (WAN)",
              ip_address="203.0.113.2", prefix_length=30,
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="routed", firewall_policy="FW_OUTSIDE_IN"),
    Interface(id=_id("fw-01.inside"), device_id=_id("fw-01"), device_name="fw-01",
              name="GigabitEthernet0/1", description="Inside (core)",
              ip_address="10.0.0.2", prefix_length=30,
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="routed", acl_out="ACL_INSIDE_OUT"),

    # ── router-core-01 ──
    Interface(id=_id("rc01.g0"), device_id=_id("router-core-01"), device_name="router-core-01",
              name="GigabitEthernet0/0/0", description="Uplink to fw-01",
              ip_address="10.0.0.1", prefix_length=30,
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="routed", acl_in="ACL_CORE_IN"),
    Interface(id=_id("rc01.g1"), device_id=_id("router-core-01"), device_name="router-core-01",
              name="GigabitEthernet0/0/1", description="Trunk to sw-dist-01",
              admin_status="up", oper_status="up", speed_mbps=10000,
              vlan_mode="trunk", trunk_vlans=[10, 20, 30, 40], native_vlan=1),
    Interface(id=_id("rc01.g2"), device_id=_id("router-core-01"), device_name="router-core-01",
              name="GigabitEthernet0/0/2", description="Trunk to sw-dist-02",
              admin_status="up", oper_status="up", speed_mbps=10000,
              vlan_mode="trunk", trunk_vlans=[10, 20, 30, 40], native_vlan=1),
    Interface(id=_id("rc01.g3"), device_id=_id("router-core-01"), device_name="router-core-01",
              name="GigabitEthernet0/0/3", description="Crosslink to router-core-02 (DISABLED)",
              admin_status="disabled", oper_status="down", speed_mbps=10000,
              vlan_mode="routed"),

    # ── router-core-02 ──
    Interface(id=_id("rc02.ge0"), device_id=_id("router-core-02"), device_name="router-core-02",
              name="ge-0/0/0", description="Crosslink to router-core-01 (DISABLED)",
              admin_status="disabled", oper_status="down", speed_mbps=10000,
              vlan_mode="routed"),

    # ── sw-dist-01 ──
    Interface(id=_id("sd01.g1"), device_id=_id("sw-dist-01"), device_name="sw-dist-01",
              name="1:1", description="Uplink to router-core-01",
              admin_status="up", oper_status="up", speed_mbps=10000,
              vlan_mode="trunk", trunk_vlans=[10, 20, 30, 40]),
    Interface(id=_id("sd01.g2"), device_id=_id("sw-dist-01"), device_name="sw-dist-01",
              name="1:2", description="Downlink to sw-acc-01",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="trunk", trunk_vlans=[10, 20]),
    Interface(id=_id("sd01.g3"), device_id=_id("sw-dist-01"), device_name="sw-dist-01",
              name="1:3", description="Downlink to sw-acc-02",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="trunk", trunk_vlans=[10, 20], acl_in="ACL_ACCESS_SW"),

    # ── sw-dist-02 ──
    Interface(id=_id("sd02.g1"), device_id=_id("sw-dist-02"), device_name="sw-dist-02",
              name="GigabitEthernet1/0/1", description="Uplink to router-core-01",
              admin_status="up", oper_status="up", speed_mbps=10000,
              vlan_mode="trunk", trunk_vlans=[10, 20, 30, 40]),
    Interface(id=_id("sd02.g2"), device_id=_id("sw-dist-02"), device_name="sw-dist-02",
              name="GigabitEthernet1/0/2", description="Downlink to sw-acc-03",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="trunk", trunk_vlans=[30, 40]),

    # ── sw-acc-01 ──
    Interface(id=_id("sa01.g1"), device_id=_id("sw-acc-01"), device_name="sw-acc-01",
              name="GigabitEthernet0/1", description="Uplink to sw-dist-01",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="trunk", trunk_vlans=[10, 20]),
    Interface(id=_id("sa01.g2"), device_id=_id("sw-acc-01"), device_name="sw-acc-01",
              name="GigabitEthernet0/2", description="server-01",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="access", vlan_id=10),

    # ── sw-acc-02 ──
    Interface(id=_id("sa02.g1"), device_id=_id("sw-acc-02"), device_name="sw-acc-02",
              name="GigabitEthernet0/1", description="Uplink to sw-dist-01",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="trunk", trunk_vlans=[10, 20]),
    Interface(id=_id("sa02.g2"), device_id=_id("sw-acc-02"), device_name="sw-acc-02",
              name="GigabitEthernet0/2", description="server-02",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="access", vlan_id=20),

    # ── sw-acc-03 ──
    Interface(id=_id("sa03.g1"), device_id=_id("sw-acc-03"), device_name="sw-acc-03",
              name="1/1/1", description="Uplink to sw-dist-02",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="trunk", trunk_vlans=[30, 40]),
    Interface(id=_id("sa03.g2"), device_id=_id("sw-acc-03"), device_name="sw-acc-03",
              name="1/1/2", description="jumpbox-01",
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="access", vlan_id=30),

    # ── Servers / hosts ──
    Interface(id=_id("srv01.eth0"), device_id=_id("server-01"), device_name="server-01",
              name="eth0", ip_address="10.10.10.101", prefix_length=24,
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="access"),
    Interface(id=_id("srv02.eth0"), device_id=_id("server-02"), device_name="server-02",
              name="eth0", ip_address="10.10.20.101", prefix_length=24,
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="access"),
    Interface(id=_id("jmp01.eth0"), device_id=_id("jumpbox-01"), device_name="jumpbox-01",
              name="Ethernet0", ip_address="10.10.30.10", prefix_length=24,
              admin_status="up", oper_status="up", speed_mbps=1000,
              vlan_mode="access"),
]


# ─────────────────────────────────────────────────────────────────
# CONNECTIONS
# Determines edge colour:
#  status=disabled                    → black dashed
#  has_acl=True or has_firewall=True  → orange
#  link_type=trunk                    → thick blue
#  otherwise up                       → green
# ─────────────────────────────────────────────────────────────────
CONNECTIONS: list[Connection] = [
    # internet → fw-01  (ORANGE — firewall policy on WAN)
    Connection(
        id=_id("conn.internet.fw01"),
        src_device_id=_id("internet"), src_device_name="internet", src_interface="wan0",
        dst_device_id=_id("fw-01"), dst_device_name="fw-01", dst_interface="GigabitEthernet0/0",
        link_type="routed", status="up", has_firewall=True, bandwidth_mbps=1000,
        description="WAN uplink — firewall policy applied",
    ),
    # fw-01 → router-core-01  (ORANGE — ACL on inside interface)
    Connection(
        id=_id("conn.fw01.rc01"),
        src_device_id=_id("fw-01"), src_device_name="fw-01", src_interface="GigabitEthernet0/1",
        dst_device_id=_id("router-core-01"), dst_device_name="router-core-01",
        dst_interface="GigabitEthernet0/0/0",
        link_type="routed", status="up", has_acl=True, bandwidth_mbps=1000,
        description="Core uplink — ACL_CORE_IN applied",
    ),
    # router-core-01 → sw-dist-01  (BLUE TRUNK)
    Connection(
        id=_id("conn.rc01.sd01"),
        src_device_id=_id("router-core-01"), src_device_name="router-core-01",
        src_interface="GigabitEthernet0/0/1",
        dst_device_id=_id("sw-dist-01"), dst_device_name="sw-dist-01", dst_interface="1:1",
        link_type="trunk", status="up", bandwidth_mbps=10000,
        description="10G trunk — VLANs 10,20,30,40",
    ),
    # router-core-01 → sw-dist-02  (BLUE TRUNK)
    Connection(
        id=_id("conn.rc01.sd02"),
        src_device_id=_id("router-core-01"), src_device_name="router-core-01",
        src_interface="GigabitEthernet0/0/2",
        dst_device_id=_id("sw-dist-02"), dst_device_name="sw-dist-02",
        dst_interface="GigabitEthernet1/0/1",
        link_type="trunk", status="up", bandwidth_mbps=10000,
        description="10G trunk — VLANs 10,20,30,40",
    ),
    # router-core-01 ←→ router-core-02  (BLACK DASHED — disabled)
    Connection(
        id=_id("conn.rc01.rc02"),
        src_device_id=_id("router-core-01"), src_device_name="router-core-01",
        src_interface="GigabitEthernet0/0/3",
        dst_device_id=_id("router-core-02"), dst_device_name="router-core-02",
        dst_interface="ge-0/0/0",
        link_type="crosslink", status="disabled", bandwidth_mbps=10000,
        description="Backup core crosslink — admin shutdown",
    ),
    # sw-dist-01 → sw-acc-01  (BLUE TRUNK)
    Connection(
        id=_id("conn.sd01.sa01"),
        src_device_id=_id("sw-dist-01"), src_device_name="sw-dist-01", src_interface="1:2",
        dst_device_id=_id("sw-acc-01"), dst_device_name="sw-acc-01", dst_interface="GigabitEthernet0/1",
        link_type="trunk", status="up", bandwidth_mbps=1000,
        description="Access trunk — VLANs 10,20",
    ),
    # sw-dist-01 → sw-acc-02  (ORANGE TRUNK — ACL applied)
    Connection(
        id=_id("conn.sd01.sa02"),
        src_device_id=_id("sw-dist-01"), src_device_name="sw-dist-01", src_interface="1:3",
        dst_device_id=_id("sw-acc-02"), dst_device_name="sw-acc-02", dst_interface="GigabitEthernet0/1",
        link_type="trunk", status="up", has_acl=True, bandwidth_mbps=1000,
        description="Access trunk — VLANs 10,20 + ACL_ACCESS_SW",
    ),
    # sw-dist-02 → sw-acc-03  (BLUE TRUNK)
    Connection(
        id=_id("conn.sd02.sa03"),
        src_device_id=_id("sw-dist-02"), src_device_name="sw-dist-02",
        src_interface="GigabitEthernet1/0/2",
        dst_device_id=_id("sw-acc-03"), dst_device_name="sw-acc-03", dst_interface="1/1/1",
        link_type="trunk", status="up", bandwidth_mbps=1000,
        description="Access trunk — VLANs 30,40",
    ),
    # sw-acc-01 → server-01  (GREEN — clean access port)
    Connection(
        id=_id("conn.sa01.srv01"),
        src_device_id=_id("sw-acc-01"), src_device_name="sw-acc-01",
        src_interface="GigabitEthernet0/2",
        dst_device_id=_id("server-01"), dst_device_name="server-01", dst_interface="eth0",
        link_type="access", status="up", bandwidth_mbps=1000,
        description="Server-01 access — VLAN 10",
    ),
    # sw-acc-02 → server-02  (GREEN — clean access port)
    Connection(
        id=_id("conn.sa02.srv02"),
        src_device_id=_id("sw-acc-02"), src_device_name="sw-acc-02",
        src_interface="GigabitEthernet0/2",
        dst_device_id=_id("server-02"), dst_device_name="server-02", dst_interface="eth0",
        link_type="access", status="up", bandwidth_mbps=1000,
        description="Server-02 access — VLAN 20",
    ),
    # sw-acc-03 → jumpbox-01  (GREEN — clean access port)
    Connection(
        id=_id("conn.sa03.jmp01"),
        src_device_id=_id("sw-acc-03"), src_device_name="sw-acc-03", src_interface="1/1/2",
        dst_device_id=_id("jumpbox-01"), dst_device_name="jumpbox-01", dst_interface="Ethernet0",
        link_type="access", status="up", bandwidth_mbps=1000,
        description="Jumpbox access — VLAN 30",
    ),
]


# ─────────────────────────────────────────────────────────────────
# ACLs
# ─────────────────────────────────────────────────────────────────
ACLS: list[Acl] = [
    # ── ACL_CORE_IN on router-core-01 Gi0/0/0 (inbound from fw-01) ──
    Acl(
        id=_id("acl.rc01.core_in"),
        device_id=_id("router-core-01"), device_name="router-core-01",
        name="ACL_CORE_IN", acl_type="extended",
        rules=[
            AclRule(sequence=10, action="permit", protocol="tcp",
                    src_network="any", dst_network="10.0.0.0/8",
                    dst_port=22, description="Allow SSH inbound"),
            AclRule(sequence=20, action="permit", protocol="tcp",
                    src_network="any", dst_network="10.0.0.0/8",
                    dst_port=443, description="Allow HTTPS inbound"),
            AclRule(sequence=30, action="permit", protocol="icmp",
                    src_network="any", dst_network="any",
                    description="Allow ICMP (ping)"),
            AclRule(sequence=40, action="permit", protocol="udp",
                    src_network="any", dst_network="any",
                    dst_port=161, description="Allow SNMP"),
            AclRule(sequence=50, action="deny", protocol="tcp",
                    src_network="any", dst_network="any",
                    dst_port=23, description="Block Telnet"),
            AclRule(sequence=60, action="deny", protocol="tcp",
                    src_network="any", dst_network="any",
                    dst_port=80, description="Block plain HTTP"),
            AclRule(sequence=1000, action="deny", protocol="ip",
                    src_network="any", dst_network="any",
                    description="Implicit deny all"),
        ]
    ),
    # ── ACL_INSIDE_OUT on fw-01 Gi0/1 (outbound toward core) ──
    Acl(
        id=_id("acl.fw01.inside_out"),
        device_id=_id("fw-01"), device_name="fw-01",
        name="ACL_INSIDE_OUT", acl_type="extended",
        rules=[
            AclRule(sequence=10, action="permit", protocol="tcp",
                    src_network="10.0.0.0/8", dst_network="any",
                    established=True, description="Permit established TCP return traffic"),
            AclRule(sequence=20, action="permit", protocol="icmp",
                    src_network="any", dst_network="any",
                    description="Permit ICMP"),
            AclRule(sequence=30, action="permit", protocol="tcp",
                    src_network="10.10.30.0/24", dst_network="any",
                    dst_port=22, description="Jumpbox SSH to anywhere"),
            AclRule(sequence=1000, action="deny", protocol="ip",
                    src_network="any", dst_network="any",
                    description="Implicit deny all"),
        ]
    ),
    # ── ACL_ACCESS_SW on sw-dist-01 port 1:3 (to sw-acc-02) ──
    Acl(
        id=_id("acl.sd01.access_sw"),
        device_id=_id("sw-dist-01"), device_name="sw-dist-01",
        name="ACL_ACCESS_SW", acl_type="extended",
        rules=[
            AclRule(sequence=10, action="permit", protocol="tcp",
                    src_network="10.10.20.0/24", dst_network="any",
                    dst_port=22, description="server-02 SSH"),
            AclRule(sequence=20, action="permit", protocol="tcp",
                    src_network="10.10.20.0/24", dst_network="any",
                    dst_port=443, description="server-02 HTTPS"),
            AclRule(sequence=30, action="deny", protocol="tcp",
                    src_network="10.10.20.0/24", dst_network="any",
                    dst_port=3389, description="Block RDP from server segment"),
            AclRule(sequence=1000, action="deny", protocol="ip",
                    src_network="any", dst_network="any",
                    description="Implicit deny all"),
        ]
    ),
]


def all_data() -> dict:
    """Return all sample data as a dict keyed by type."""
    return {
        "devices": DEVICES,
        "interfaces": INTERFACES,
        "connections": CONNECTIONS,
        "acls": ACLS,
    }
