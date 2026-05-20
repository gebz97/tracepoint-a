// models/models.go
package main

import (
	"encoding/json"
	"github.com/lib/pq"
	"time"
)

type AdapterType struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type ClusterType struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type HypervisorType struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type HostStatus struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type PowerState struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type Environment struct {
	ID          int    `gorm:"primaryKey;autoIncrement"`
	Name        string `gorm:"uniqueIndex;not null"`
	Abbr        string `gorm:"uniqueIndex;not null"`
	Description string
}

type NetworkType struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type DatastoreType struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type DiskFormat struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type CpuArch struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type PlatformVendor struct {
	ID   int    `gorm:"primaryKey;autoIncrement"`
	Name string `gorm:"uniqueIndex;not null"`
}

type VMStatusType struct {
	ID   int `gorm:"primaryKey;autoIncrement"`
	Name string
	Abbr string
}

type VMFunctionType struct {
	ID          int    `gorm:"primaryKey;autoIncrement"`
	Name        string `gorm:"uniqueIndex;not null"`
	Abbr        string `gorm:"uniqueIndex;not null"`
	Description string
}

type VMSpecialContext struct {
	ID          int    `gorm:"primaryKey;autoIncrement"`
	Name        string `gorm:"uniqueIndex;not null"`
	Abbr        string `gorm:"uniqueIndex;not null"`
	Description string
}

// --- Core entities ---

type Datacenter struct {
	ID             int    `gorm:"primaryKey;autoIncrement"`
	DatacenterName string `gorm:"uniqueIndex;not null"`
	Location       string
	Description    string
	Metadata       json.RawMessage `gorm:"type:jsonb"`
}

type Vendor struct {
	ID             int    `gorm:"primaryKey;autoIncrement"`
	Name           string `gorm:"uniqueIndex;not null"`
	Country        string
	Description    string
	PrimaryContact string
}

type SoftwareLicense struct {
	ID        int    `gorm:"primaryKey;autoIncrement"`
	Name      string `gorm:"uniqueIndex;not null"`
	Shortname string `gorm:"uniqueIndex"`
}

type SoftwarePackage struct {
	ID        int64  `gorm:"primaryKey;autoIncrement"`
	Fullname  string `gorm:"uniqueIndex;not null"`
	Name      string
	Version   string
	Arch      string
	LicenseID int
	License   *SoftwareLicense `gorm:"foreignKey:LicenseID"`
	VendorID  int              `gorm:"column:vendor"`
	Vendor    *Vendor          `gorm:"foreignKey:VendorID"`
}

type OperatingSystem struct {
	ID           int    `gorm:"primaryKey;autoIncrement"`
	Fullname     string `gorm:"uniqueIndex;not null"`
	Name         string
	Version      string
	MajorVersion string
	MinorVersion string
	Vendor       string
}

type Contact struct {
	ID       int             `gorm:"primaryKey;autoIncrement"`
	FullName string          `gorm:"not null"`
	Email    string          `gorm:"uniqueIndex;not null"`
	Metadata json.RawMessage `gorm:"type:jsonb"`
}

type CostCenter struct {
	ID             int    `gorm:"primaryKey;autoIncrement"`
	CostCenterCode string `gorm:"uniqueIndex;not null"`
	CostCenterName string `gorm:"not null"`
	Description    string
}

type Team struct {
	ID          int    `gorm:"primaryKey;autoIncrement"`
	TeamName    string `gorm:"uniqueIndex;not null"`
	Description string
	Email       string
	Metadata    json.RawMessage `gorm:"type:jsonb"`
	Contacts    []*Contact      `gorm:"many2many:team_contacts;"`
}

type TeamContact struct {
	TeamID    int `gorm:"primaryKey"`
	ContactID int `gorm:"primaryKey"`
	Role      string
}

type Project struct {
	ID           int `gorm:"primaryKey;autoIncrement"`
	TeamID       int `gorm:"not null"`
	Team         Team
	CostCenterID int
	CostCenter   *CostCenter
	ProjectName  string `gorm:"uniqueIndex;not null"`
	Description  string
	StartDate    *time.Time
	EndDate      *time.Time
	Metadata     json.RawMessage `gorm:"type:jsonb"`
}

type Service struct {
	ID          int `gorm:"primaryKey;autoIncrement"`
	TeamID      int `gorm:"not null"`
	Team        Team
	ServiceName string `gorm:"uniqueIndex;not null"`
	Description string
	Metadata    json.RawMessage `gorm:"type:jsonb"`
}

type Cluster struct {
	ID               int `gorm:"primaryKey;autoIncrement"`
	DatacenterID     int `gorm:"not null;index"`
	Datacenter       Datacenter
	ClusterTypeID    int `gorm:"index"`
	ClusterType      *ClusterType
	ClusterName      string `gorm:"not null;uniqueIndex:uni_cluster_dc"`
	HighAvailability bool   `gorm:"default:false;not null"`
	LoadBalancing    bool   `gorm:"default:false;not null"`
	Description      string
	Features         json.RawMessage `gorm:"type:jsonb"`
}

type ComputePool struct {
	ID          int `gorm:"primaryKey;autoIncrement"`
	ClusterID   int `gorm:"not null;index"`
	Cluster     Cluster
	ParentID    int
	Parent      *ComputePool `gorm:"foreignKey:ParentID"`
	PoolName    string       `gorm:"not null;uniqueIndex:uni_pool_cluster"`
	CpuShares   int
	CpuLimitMhz int
	MemShares   int
	MemLimitMb  int64
	PlatformRef string
}

type Network struct {
	ID            int `gorm:"primaryKey;autoIncrement"`
	NetworkTypeID int `gorm:"index"`
	NetworkType   *NetworkType
	NetworkName   string `gorm:"not null;uniqueIndex:uni_network"`
	VlanID        int    `gorm:"uniqueIndex:uni_network"`
	VirtualSwitch string
	CIDR          string
	Gateway       string
	DNSServers    pq.StringArray `gorm:"type:text[]"`
	PlatformRef   string
	Metadata      json.RawMessage `gorm:"type:jsonb"`
}

type Datastore struct {
	ID              int `gorm:"primaryKey;autoIncrement"`
	DatacenterID    int `gorm:"not null;index"`
	Datacenter      Datacenter
	DatastoreTypeID int `gorm:"not null;index"`
	DatastoreType   DatastoreType
	DatastoreName   string `gorm:"uniqueIndex;not null"`
	DsPath          string
	TotalGB         int64
	UsedGB          int64
	// FreeGB is a generated column, omit from writes
	FreeGB             int64 `gorm:"<-:false"`
	ThinProvisioned    bool  `gorm:"default:true;not null"`
	ReplicationEnabled bool  `gorm:"default:false;not null"`
	PlatformRef        string
	Metadata           json.RawMessage `gorm:"type:jsonb"`
}

type HypervisorHost struct {
	ID                int `gorm:"primaryKey;autoIncrement"`
	ClusterID         int `gorm:"not null;index"`
	Cluster           Cluster
	HypervisorTypeID  int `gorm:"not null;index"`
	HypervisorType    HypervisorType
	PlatformVendorID  int `gorm:"index"`
	PlatformVendor    *PlatformVendor
	StatusID          int `gorm:"not null;index"`
	Status            HostStatus
	Hostname          string `gorm:"uniqueIndex;not null"`
	IPv4              string `gorm:"uniqueIndex;not null"`
	IpmiIP            string
	HypervisorVersion string
	PlatformRef       string
	Manufacturer      string
	Model             string
	SerialNumber      string
	CpuModel          string
	CpuSockets        int
	CpuCores          int
	MemoryMB          int64
	MaintenanceMode   bool            `gorm:"default:false;not null"`
	Metadata          json.RawMessage `gorm:"type:jsonb"`
	Datastores        []*Datastore    `gorm:"many2many:datastore_hosts;"`
	Networks          []*Network      `gorm:"many2many:network_hosts;"`
}

type DatastoreHost struct {
	DatastoreID int       `gorm:"primaryKey"`
	HostID      int       `gorm:"primaryKey"`
	MountedAt   time.Time `gorm:"default:now();not null"`
	ReadOnly    bool      `gorm:"default:false;not null"`
}

type NetworkHost struct {
	NetworkID int `gorm:"primaryKey"`
	HostID    int `gorm:"primaryKey"`
}

type Template struct {
	ID           int `gorm:"primaryKey;autoIncrement"`
	DatastoreID  int
	Datastore    *Datastore
	ArchID       int
	Arch         *CpuArch
	TemplateName string `gorm:"uniqueIndex;not null"`
	Distribution string
	OsVersion    string
	PlatformRef  string
	Notes        string
}

type VM struct {
	ID               int `gorm:"primaryKey;autoIncrement"`
	HypervisorHostID int `gorm:"index"`
	HypervisorHost   *HypervisorHost
	ComputePoolID    int `gorm:"index"`
	ComputePool      *ComputePool
	TemplateID       int
	Template         *Template
	PowerStateID     int `gorm:"index"`
	PowerState       *PowerState
	CostCenterID     int
	CostCenter       *CostCenter
	TeamID           int
	Team             *Team
	ProjectID        int
	Project          *Project
	EnvironmentID    int `gorm:"index"`
	Environment      *Environment
	ServiceID        int
	Service          *Service
	ArchID           int
	Arch             *CpuArch
	OsID             int
	Os               *OperatingSystem
	Host             string
	VMStatus         int
	VMStatusType     *VMStatusType `gorm:"foreignKey:VMStatus"`
	VMName           string        `gorm:"uniqueIndex;not null"`
	IPv4             string        `gorm:"uniqueIndex;not null"`
	Shortname        string        `gorm:"uniqueIndex"`
	FQDN             string        `gorm:"uniqueIndex"`
	VMUuid           string        `gorm:"uniqueIndex"`
	CPUs             int
	MemoryMB         int64
	StorageTotalGB   int64
	HasBackup        *bool
	HasDR            *bool
	Kernel           string
	Metadata         json.RawMessage    `gorm:"type:jsonb"`
	Packages         []*SoftwarePackage `gorm:"many2many:vm_packages;"`
}

type VMDisk struct {
	ID           int `gorm:"primaryKey;autoIncrement"`
	VMID         int `gorm:"not null;index"`
	VM           VM
	DatastoreID  int `gorm:"index"`
	Datastore    *Datastore
	DiskFormatID int `gorm:"index"`
	DiskFormat   *DiskFormat
	Label        string
	SizeGB       int64 `gorm:"not null"`
	DiskPath     string
	BootDisk     bool `gorm:"default:false;not null"`
}

type VMNIC struct {
	ID            int `gorm:"primaryKey;autoIncrement"`
	VMID          int `gorm:"not null;index"`
	VM            VM
	NetworkID     int `gorm:"index"`
	Network       *Network
	AdapterTypeID int
	AdapterType   *AdapterType
	MacAddress    string
	IPv4          string
	IPv6          string
	Connected     bool `gorm:"default:true;not null"`
}

type VMSnapshot struct {
	ID           int `gorm:"primaryKey;autoIncrement"`
	VMID         int `gorm:"not null;index"`
	VM           VM
	ParentID     int         `gorm:"index"`
	Parent       *VMSnapshot `gorm:"foreignKey:ParentID"`
	SnapshotName string      `gorm:"not null"`
	Description  string
	SizeGB       int64
	Quiesced     bool `gorm:"default:false;not null"`
	PlatformRef  string
}

type VMGroup struct {
	ID          int64 `gorm:"primaryKey;autoIncrement"`
	VMID        int   `gorm:"not null;uniqueIndex:uni_vm_group"`
	VM          VM
	Name        string `gorm:"not null;uniqueIndex:uni_vm_group"`
	GID         int
	Description string
}

type VMMount struct {
	ID           int64 `gorm:"primaryKey;autoIncrement"`
	VMID         int   `gorm:"not null;uniqueIndex:uni_vm_mount"`
	VM           VM
	Mountpoint   string         `gorm:"not null;uniqueIndex:uni_vm_mount"`
	Source       string         `gorm:"not null"`
	Fstype       string         `gorm:"not null"`
	Opts         pq.StringArray `gorm:"type:varchar[]"`
	Status       string
	InFstab      *bool
	Size         int64
	UsedLastSeen int64
	UsedPct      *float64
}

type VMUser struct {
	ID          int64 `gorm:"primaryKey;autoIncrement"`
	VMID        int   `gorm:"not null;uniqueIndex:uni_vm_user_name,uni_vm_user_uid"`
	VM          VM
	Name        string         `gorm:"not null;uniqueIndex:uni_vm_user_name"`
	UID         int            `gorm:"not null;uniqueIndex:uni_vm_user_uid"`
	PGroup      string         `gorm:"not null"`
	Groups      pq.StringArray `gorm:"type:varchar[];not null"`
	GID         int
	GIDs        pq.Int32Array `gorm:"type:int[]"`
	HasSudo     *bool
	Description string
}

type Daemon struct {
	ID               int `gorm:"primaryKey;autoIncrement"`
	VMID             int `gorm:"not null;uniqueIndex:uni_daemon"`
	VM               VM
	DaemonName       string `gorm:"not null;uniqueIndex:uni_daemon"`
	StartUser        string
	StartGroup       string
	UnitFilePath     string
	ServiceType      string
	ServiceState     string
	ServiceSubState  string
	ExecStart        string
	ExecStop         string
	ExecReload       string
	RestartPolicy    string
	RestartSec       int
	TimeoutSec       int
	WorkingDirectory string
	Wants            pq.StringArray  `gorm:"type:text[]"`
	Requires         pq.StringArray  `gorm:"type:text[]"`
	After            pq.StringArray  `gorm:"type:text[]"`
	Before           pq.StringArray  `gorm:"type:text[]"`
	Enabled          *bool           `gorm:"default:false"`
	Active           *bool           `gorm:"default:false"`
	Metadata         json.RawMessage `gorm:"type:jsonb"`
}
