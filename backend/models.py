"""
TreasureMap — Pydantic models for Elasticsearch documents.
All models mirror the ES index mappings defined in es_client.py.
"""
from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

class Device(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str                           # e.g. "router-core-01"
    hostname: str                       # FQDN or short name
    management_ip: str
    vendor: str                         # Cisco | Juniper | Extreme | Nokia | …
    model: str
    os: str                             # IOS-XE | JunOS | ExtremeXOS | SR-OS | …
    device_type: str                    # router | switch | firewall | server | host
    location: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class Interface(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str
    device_name: str
    name: str                           # e.g. "GigabitEthernet0/0/0"
    description: Optional[str] = None
    ip_address: Optional[str] = None
    prefix_length: Optional[int] = None
    mac_address: Optional[str] = None
    # admin status: up = enabled, disabled = admin-down, down = link-down
    admin_status: Literal["up", "down", "disabled"] = "up"
    oper_status: Literal["up", "down"] = "up"
    speed_mbps: Optional[int] = None
    duplex: Optional[str] = None
    # VLAN info
    vlan_mode: Literal["access", "trunk", "routed", "none"] = "none"
    vlan_id: Optional[int] = None       # for access ports
    trunk_vlans: List[int] = Field(default_factory=list)   # for trunk ports
    native_vlan: Optional[int] = None
    # ACL / firewall policy names applied to this interface
    acl_in: Optional[str] = None
    acl_out: Optional[str] = None
    firewall_policy: Optional[str] = None


# ---------------------------------------------------------------------------
# Connection  (one record per physical link, direction-agnostic)
# ---------------------------------------------------------------------------

class Connection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    src_device_id: str
    src_device_name: str
    src_interface: str
    dst_device_id: str
    dst_device_name: str
    dst_interface: str
    # Link type drives edge colour in the UI
    link_type: Literal["routed", "trunk", "access", "uplink", "crosslink", "bgp"] = "routed"
    # Effective status of the link (derived from both interface admin/oper states)
    status: Literal["up", "down", "disabled"] = "up"
    # True when at least one ACL/firewall policy touches this link
    has_acl: bool = False
    has_firewall: bool = False
    bandwidth_mbps: Optional[int] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# ACL
# ---------------------------------------------------------------------------

class AclRule(BaseModel):
    sequence: int
    action: Literal["permit", "deny"]
    protocol: str                       # ip | tcp | udp | icmp | ospf | …
    src_network: str = "any"            # CIDR or "any"
    dst_network: str = "any"
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    src_port_range: Optional[List[int]] = None   # [start, end]
    dst_port_range: Optional[List[int]] = None
    description: Optional[str] = None
    established: bool = False           # TCP established flag


class Acl(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str
    device_name: str
    name: str
    acl_type: Literal["standard", "extended", "named"] = "extended"
    rules: List[AclRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Path-finding request / response
# ---------------------------------------------------------------------------

class PathRequest(BaseModel):
    source: str           # device name, IP, or "device:interface"
    destination: str      # device name, IP, or "internet"
    protocol: Optional[str] = None     # tcp | udp | icmp | …
    dst_port: Optional[int] = None
    src_port: Optional[int] = None
    src_ip: Optional[str] = None


class HopResult(BaseModel):
    hop: int
    device_name: str
    interface_in: Optional[str] = None
    interface_out: Optional[str] = None
    link_status: str
    acl_result: Optional[str] = None   # "permit" | "deny" | "no-acl"
    acl_name: Optional[str] = None
    acl_rule_seq: Optional[int] = None
    notes: Optional[str] = None


class PathResult(BaseModel):
    found: bool
    source: str
    destination: str
    protocol: Optional[str] = None
    dst_port: Optional[int] = None
    authorized: Optional[bool] = None  # None = no ACLs evaluated
    path: List[str] = Field(default_factory=list)           # device names in order
    edges: List[str] = Field(default_factory=list)          # connection IDs in order
    hops: List[HopResult] = Field(default_factory=list)
    summary: str = ""
