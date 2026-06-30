# Project Orion

## Software Requirements Specification (SRS)

---

**Document ID:** ORION-SRS

**Version:** 0.3.0

**Status:** Draft

**Last Updated:** June 28, 2026

**Authors:**

* Elijah
* OpenAI ChatGPT

**Classification:** Internal Development

---

# Revision History

| Version | Date       | Author(s)              | Description                                 |
| ------- | ---------- | ---------------------- | ------------------------------------------- |
| 0.1.0   | 2026-06-28 | Elijah, OpenAI ChatGPT | Initial SRS created. Session One completed. |

---

# Table of Contents

1. Introduction
2. Project Overview
3. Vision
4. Goals
5. Project Scope
6. Non-Goals
7. Intended Audience
8. Terminology
9. Guiding Principles

---

# 1. Introduction

## 1.1 Purpose

Project Orion is a zero-touch infrastructure provisioning platform designed to automate the conversion of surplus and commodity computer hardware into managed virtualization infrastructure.

The project exists to eliminate repetitive deployment work while maintaining strict operator oversight for irreversible operations such as storage sanitization.

This document serves as the authoritative engineering specification for the Orion project.

No production feature shall be implemented before its behavior has been documented within this Software Requirements Specification.

---

## 1.2 Background

Building and maintaining virtualization clusters often requires repetitive manual configuration of hardware, firmware, operating systems, networking, and virtualization software.

Many organizations—and home lab operators—acquire large quantities of retired laptops and desktop systems that still possess significant computational value.

Preparing these systems manually is slow, error-prone, inconsistent, and difficult to reproduce.

Project Orion was conceived to standardize this process through automation while preserving operator control over destructive actions.

---

## 1.3 Project Mission

Project Orion exists to provide a safe, repeatable, operator-supervised provisioning platform for converting commodity computer hardware into managed Proxmox cluster resources.

The system shall minimize technician effort while maximizing deployment consistency, operational safety, and long-term maintainability.

---

# 2. Project Overview

Project Orion is not an operating system.

Project Orion is not a replacement for Proxmox.

Project Orion is an automated deployment platform responsible for preparing hardware for use within a Proxmox virtualization cluster.

The project provides tooling for:

* Hardware inspection
* Hardware validation
* Optional data recovery
* Secure storage preparation
* Automated Proxmox installation
* First-boot configuration
* Cluster enrollment
* Inventory registration
* Hardware benchmarking
* Deployment reporting

The deployment environment is distributed using bootable USB media.

The USB serves only as the deployment medium.

The Orion source code, documentation, build system, release process, and version control are maintained independently within the project's source repository.

---

# 3. Vision

The long-term vision of Project Orion is to allow a technician to transform supported computer hardware into production-ready virtualization resources using a standardized, repeatable deployment workflow.

When complete, Orion shall require minimal technician interaction after deployment has been authorized.

The deployment experience should resemble enterprise device provisioning platforms while remaining fully self-hosted and optimized for Proxmox environments.

The system shall scale from individual laboratory deployments to clusters consisting of many nodes without requiring architectural redesign.

---

# 4. Project Goals

Project Orion has the following primary objectives.

## G-001

Reduce deployment time for new cluster nodes.

---

## G-002

Standardize every deployed node.

---

## G-003

Reduce manual technician effort.

---

## G-004

Prevent accidental destruction of user data.

---

## G-005

Provide repeatable deployment workflows.

---

## G-006

Automatically configure supported hardware and operating system settings.

Examples include:

* Disable suspend on laptop lid closure.
* Configure supported battery charging limits.
* Configure supported power recovery settings.
* Apply deployment-specific operating system configuration.

---

## G-007

Automatically install and configure Proxmox VE.

---

## G-008

Automatically enroll deployed systems into the designated Proxmox cluster.

---

## G-009

Maintain centralized inventory for every deployed node.

---

## G-010

Provide complete deployment logs for auditing and troubleshooting.

---

## G-011

Support future expansion through a modular software architecture.

---

# 5. Project Scope

Version 1.0 of Project Orion includes the following major capabilities.

## Included

* Technician Console
* Hardware inspection
* Hardware validation
* Deployment readiness reports
* Optional customer data recovery
* Secure storage preparation
* Automated Proxmox installation
* Bootstrap automation
* Deployment Controller integration
* Automatic cluster enrollment
* Automatic inventory registration
* Hardware benchmarking
* Deployment reporting
* Configuration management
* Logging
* Software packaging
* USB deployment media generation

---

## Excluded

The following capabilities are outside the scope of Version 1.0.

* Cloud deployment
* Internet-hosted management
* Multi-cluster orchestration
* Windows deployment
* Consumer backup software
* Virtual machine management
* Container orchestration
* High-availability cluster management
* PXE network deployment

These capabilities may be evaluated in future releases.

---

# 6. Intended Audience

This document is intended for:

* Project developers
* System administrators
* AI coding assistants
* Software testers
* Technical reviewers
* Future project contributors

The document assumes familiarity with Linux, virtualization, networking, and software development practices.

---

# 7. Terminology

## Technician

The individual responsible for operating Orion.

---

## Technician Console

The interactive application launched from the deployment environment.

---

## Deployment Controller

The centralized service responsible for approving, configuring, registering, and provisioning new Orion nodes.

---

## Node

A successfully deployed Proxmox system managed by Orion.

---

## Inspection

The non-destructive examination of hardware prior to deployment.

---

## Recovery

The optional extraction of user data before destructive operations occur.

---

## Preparation

The operator-approved process responsible for securely sanitizing deployment storage.

---

## Provisioning

The automated installation and configuration of Proxmox.

---

## Bootstrap

The first-boot configuration process responsible for preparing a node for production operation.

---

## Inventory

The database of deployed systems maintained by the Deployment Controller.

---

## Deployment Session

The complete lifecycle beginning when Orion is launched and ending when deployment either succeeds or terminates.

---

# 8. Guiding Principles

Every engineering decision shall follow these principles.

---

## GP-001

Safety Before Automation

Automation shall never perform irreversible actions without explicit operator authorization.

---

## GP-002

Operator Supervision

Orion automates work.

Technicians authorize irreversible decisions.

---

## GP-003

Configuration Over Hardcoding

Deployment behavior shall be controlled through configuration rather than embedded source code values whenever practical.

---

## GP-004

Modular Design

Each subsystem shall perform one clearly defined responsibility.

---

## GP-005

Observability

Every significant operation shall be logged.

Deployment history shall be fully traceable.

---

## GP-006

Repeatability

Equivalent hardware deployed using equivalent configurations shall produce equivalent results.

---

## GP-007

Expandability

Future functionality shall be addable without requiring major architectural redesign.

---

## GP-008

Hardware Preservation

Supported hardware shall be configured to maximize long-term reliability.

Where technically possible Orion shall:

* Prevent suspend on lid closure.
* Configure supported battery charging thresholds.
* Configure supported firmware power settings.
* Report unsupported firmware features without failing deployment unless required for safe operation.

---

## GP-009

Centralized Management

Nodes shall receive deployment configuration from the Deployment Controller.

Installer media shall not contain permanently assigned deployment identities.

---

## GP-010

Documentation First

Every major feature shall be documented before implementation.

The Software Requirements Specification is the authoritative definition of project behavior.

---

# Session One Completion

The following project foundations have been established.

* Project purpose
* Project mission
* Project overview
* Long-term vision
* Goals
* Project scope
* Non-goals
* Intended audience
* Standard terminology
* Engineering principles

These sections define **what Orion is**.

Future revisions of this document will define **how Orion works**.

---

# System Architecture

---

# 9. System Architecture

## 9.1 Overview

Project Orion shall be implemented as a modular software platform composed of independent subsystems, each responsible for a single area of functionality.

The architecture shall prioritize:

* Modularity
* Maintainability
* Testability
* Expandability
* Operator safety
* Configuration-driven behavior

Subsystems shall communicate through well-defined interfaces and shall avoid unnecessary dependencies on one another.

No subsystem shall assume internal implementation details of another subsystem.

---

## 9.2 High-Level System Architecture

Project Orion consists of four primary components.

```
                +---------------------------+
                |     Source Repository     |
                |                           |
                |  Documentation            |
                |  Source Code              |
                |  Build Scripts            |
                |  Tests                    |
                +------------+--------------+
                             |
                             |
                     Build Release
                             |
                             V
                +---------------------------+
                |     Technician USB        |
                |                           |
                | Technician Console        |
                | Recovery Workflow         |
                | Provisioning Workflow     |
                +------------+--------------+
                             |
                             |
                      Ethernet Connection
                             |
                             V
                +---------------------------+
                | Deployment Controller     |
                |                           |
                | Node Approval             |
                | Configuration             |
                | Inventory                 |
                | Deployment Policies       |
                +------------+--------------+
                             |
                             |
                             V
                +---------------------------+
                |     Proxmox Cluster       |
                |                           |
                | Registered Nodes          |
                | Shared Storage            |
                | Virtual Machines          |
                +---------------------------+
```

---

# 9.3 Repository Layout

The Project Orion repository is the authoritative source for all project artifacts.

The repository shall contain:

* Documentation
* Source code
* Build scripts
* Configuration
* Testing
* Release artifacts

The repository shall **not** depend upon the deployment USB for development.

The deployment USB shall be generated from the repository during the release process.

---

# 9.4 Deployment Media

The Orion deployment USB is a release artifact.

It is not the development environment.

It is not the source repository.

The USB shall contain only the components necessary to execute deployment workflows.

Development shall occur exclusively within the Project Orion repository.

---

# 9.5 Deployment Workflows

Version 1.0 shall support two independent deployment workflows.

These workflows share common software components but serve different operational purposes.

---

## Workflow A

### Device Retirement

Purpose:

Safely prepare previously owned hardware for reuse.

Primary responsibilities:

* Hardware inspection
* Drive identification
* Optional data recovery
* Recovery verification
* Secure storage sanitization
* Sanitization verification
* Retirement reporting

Workflow A performs **no operating system installation**.

Upon completion, the device contains no recoverable customer data.

---

## Workflow B

### Orion Node Provisioning

Purpose:

Transform prepared hardware into a managed Orion node.

Primary responsibilities:

* Hardware validation
* Network validation
* Proxmox installation
* Bootstrap automation
* Operating system configuration
* Deployment Controller communication
* Cluster enrollment
* Inventory registration
* Benchmark execution
* Deployment verification

Workflow B assumes storage has already been prepared.

---

# 9.6 Technician Console

The Technician Console is the primary operator interface.

It shall be responsible for:

* Launching deployment workflows
* Displaying inspection results
* Displaying deployment progress
* Displaying warnings
* Displaying failures
* Requesting operator confirmation
* Generating deployment reports

The Technician Console shall serve as the single user-facing application.

Subsystems shall not present independent interfaces to the operator.

---

# 9.7 Deployment Controller

The Deployment Controller is the centralized management service responsible for coordinating node enrollment.

Responsibilities include:

* Authenticating new nodes
* Assigning node identities
* Assigning hostnames
* Providing deployment configuration
* Managing deployment policies
* Registering inventory
* Recording deployment history
* Approving cluster enrollment

The Deployment Controller shall act as the authoritative source for node identity.

---

# 9.8 Configuration System

Project Orion shall utilize a centralized configuration system.

Configuration shall be stored separately from application logic.

Configuration files shall define:

* Deployment settings
* Cluster settings
* Network settings
* Logging settings
* Benchmark settings
* Recovery settings
* Safety settings

Configuration changes shall not require source code modification.

---

# 9.9 Logging System

Every subsystem shall utilize the centralized logging framework.

Logs shall include:

* Timestamp
* Subsystem
* Severity
* Event description
* Result
* Optional diagnostic information

Logs shall be suitable for troubleshooting and deployment auditing.

---

# 9.10 Inventory System

Every successfully deployed node shall be registered.

Inventory records shall include, at minimum:

* Manufacturer
* Model
* CPU
* RAM
* Storage
* MAC address
* Serial number
* Deployment date
* Benchmark results
* Current deployment status

Future versions may extend the inventory schema without affecting existing deployments.

---

# 9.11 Benchmark System

Following successful deployment, Orion shall evaluate node performance.

Benchmarking shall include:

* CPU performance
* Memory performance
* Storage performance
* Network performance
* Thermal monitoring

Benchmark results shall be submitted to the Deployment Controller.

---

# 9.12 Hardware Configuration

During provisioning, Orion shall configure supported hardware and operating system settings to improve long-term operational reliability.

Examples include:

* Preventing suspend when the laptop lid is closed.
* Configuring supported battery charging thresholds.
* Configuring power recovery behavior.
* Applying operating system power management policies.

Where firmware interfaces are unavailable, Orion shall record the limitation and continue deployment when safe.

---

# 9.13 Networking

Workflow B requires Ethernet connectivity.

Prior to deployment Orion shall verify:

* Physical Ethernet link
* IP address assignment
* Reachability of the Deployment Controller
* Reachability of the target Proxmox cluster

Deployment shall pause until networking requirements are satisfied.

---

# 9.14 Safety Architecture

Irreversible actions shall require explicit operator approval.

Protected operations include:

* Storage sanitization
* Permanent deletion
* Firmware modification
* Deployment cancellation after destructive operations have begun

Operator approval shall be obtained through the Technician Console.

---

# 9.15 Build System

Project Orion shall be developed independently of deployment media.

The build system shall:

* Validate project structure
* Execute automated testing
* Package deployment assets
* Generate release artifacts
* Produce Technician USB contents

The build system shall not require manual modification of deployment files.

---

# 10. Core Components

## 10.1 Overview

Project Orion is composed of independent software subsystems.

Each subsystem is responsible for a single area of functionality and communicates with other subsystems through well-defined interfaces.

Subsystems shall remain as independent as practical to simplify maintenance, testing, and future expansion.

---

## 10.2 Technician Console

The Technician Console is the primary user interface of Project Orion.

Responsibilities include:

* Present deployment workflows
* Display hardware inspection results
* Request operator confirmation
* Display deployment progress
* Display deployment reports
* Display warnings and errors
* Launch deployment workflows

The Technician Console shall be the only application directly operated by the technician.

---

## 10.3 Inspection Engine

The Inspection Engine is responsible for collecting hardware information without modifying the target system.

Responsibilities include:

* CPU identification
* Memory detection
* Storage detection
* SMART health evaluation
* Battery information
* Network adapter detection
* Firmware capability detection
* Virtualization support detection

Inspection operations shall never modify user data.

---

## 10.4 Recovery Engine

The Recovery Engine provides optional recovery of user data prior to storage sanitization.

Responsibilities include:

* File discovery
* User file selection
* File copying
* Recovery verification
* Recovery reporting

Recovery is optional.

No destructive operations shall occur while Recovery is active.

---

## 10.5 Preparation Engine

The Preparation Engine is responsible for preparing storage devices for reuse.

Responsibilities include:

* Target disk verification
* Secure sanitization
* Verification of sanitization
* Storage reporting

Preparation requires explicit operator approval before execution.

---

## 10.6 Provisioning Engine

The Provisioning Engine installs Proxmox VE and prepares the operating system for production use.

Responsibilities include:

* Storage partitioning
* Proxmox installation
* Initial configuration
* Package installation
* Update installation

Provisioning shall execute without additional technician interaction once authorized.

---

## 10.7 Bootstrap Engine

The Bootstrap Engine executes after the first successful operating system boot.

Responsibilities include:

* Operating system configuration
* Power configuration
* Lid behavior configuration
* Supported battery configuration
* SSH configuration
* Deployment Controller registration
* Cluster enrollment

Bootstrap concludes when the node is ready for production.

---

## 10.8 Deployment Controller

The Deployment Controller coordinates cluster enrollment.

Responsibilities include:

* Authenticate nodes
* Assign hostnames
* Assign node identifiers
* Distribute configuration
* Register inventory
* Record deployment history
* Apply deployment policy

The Deployment Controller is the authoritative source for deployment identity.

---

## 10.9 Inventory Engine

The Inventory Engine records hardware and deployment metadata.

Responsibilities include:

* Hardware inventory
* Deployment history
* Benchmark storage
* Status reporting
* Asset tracking

Inventory information shall remain associated with each deployed node throughout its lifecycle.

---

## 10.10 Benchmark Engine

The Benchmark Engine evaluates newly deployed hardware.

Responsibilities include:

* CPU benchmarking
* Memory benchmarking
* Storage benchmarking
* Network benchmarking
* Thermal monitoring

Benchmark results shall be submitted to the Deployment Controller.

---

## 10.11 Configuration Engine

The Configuration Engine loads, validates, and distributes Orion configuration.

Responsibilities include:

* Load configuration files
* Validate schema
* Provide configuration to subsystems
* Detect invalid configuration
* Maintain version compatibility

Configuration shall be external to application source code.

---

## 10.12 Logging Engine

The Logging Engine provides centralized event recording.

Responsibilities include:

* Event logging
* Error logging
* Warning logging
* Deployment history
* Diagnostic information

All Orion subsystems shall utilize the Logging Engine.

---

## 10.13 Networking Engine

The Networking Engine manages communication with external systems.

Responsibilities include:

* Ethernet detection
* Network validation
* Deployment Controller communication
* Cluster communication
* Connectivity verification

Provisioning shall not proceed unless networking requirements have been satisfied.

---

## 10.14 Build System

The Build System produces Orion release artifacts.

Responsibilities include:

* Validate project structure
* Execute automated tests
* Package deployment media
* Produce release archives
* Generate deployment USB contents

Development shall occur within the repository.

Deployment media shall always be generated by the Build System.

---

## 10.15 Component Relationships

The overall software architecture follows the sequence below.

```text
Technician Console
        │
        ▼
Deployment Workflow
        │
        ▼
Inspection Engine
        │
        ▼
Recovery Engine (optional)
        │
        ▼
Preparation Engine
        │
        ▼
Provisioning Engine
        │
        ▼
Bootstrap Engine
        │
        ▼
Deployment Controller
        │
        ▼
Inventory + Benchmark
```

Each subsystem shall expose clearly defined interfaces and shall avoid unnecessary coupling to other subsystems.

Future Orion releases may introduce additional components without modifying existing subsystem responsibilities.

# 11. Functional Requirements

## 11.1 Requirement Conventions

Every functional requirement within Project Orion shall be assigned a unique identifier.

Requirement identifiers follow the format:

```
REQ-[Subsystem]-###
```

Examples:

* REQ-TC-001
* REQ-INS-014
* REQ-REC-008

Each requirement shall define a single observable behavior.

Each requirement shall be independently testable.

---

# 11.2 Technician Console Requirements

## Overview

The Technician Console is the primary interface presented to the technician throughout every Orion deployment session.

The Technician Console is responsible for coordinating deployment workflows while maintaining operator awareness and control.

---

### REQ-TC-001

The Technician Console shall launch automatically after the Orion deployment environment has booted successfully.

---

### REQ-TC-002

The Technician Console shall display the current Orion software version.

---

### REQ-TC-003

The Technician Console shall display the current deployment media version.

---

### REQ-TC-004

The Technician Console shall display the current system date and time.

---

### REQ-TC-005

The Technician Console shall display the currently detected target computer.

---

### REQ-TC-006

The Technician Console shall provide access to the Device Retirement workflow.

---

### REQ-TC-007

The Technician Console shall provide access to the Orion Node Provisioning workflow.

---

### REQ-TC-008

The Technician Console shall provide access to deployment logs.

---

### REQ-TC-009

The Technician Console shall display deployment progress during long-running operations.

---

### REQ-TC-010

The Technician Console shall display warnings separately from informational messages.

---

### REQ-TC-011

The Technician Console shall display errors separately from warnings.

---

### REQ-TC-012

The Technician Console shall prevent destructive operations from beginning until all required operator confirmations have been completed.

---

### REQ-TC-013

The Technician Console shall generate a deployment summary upon completion of every deployment session.

---

# 11.3 Inspection Engine Requirements

## Overview

The Inspection Engine evaluates hardware without modifying the target system.

Inspection operations shall be read-only.

---

### REQ-INS-001

The Inspection Engine shall enumerate all installed processors.

---

### REQ-INS-002

The Inspection Engine shall identify processor manufacturer, model, architecture, and virtualization capabilities.

---

### REQ-INS-003

The Inspection Engine shall enumerate installed memory modules.

---

### REQ-INS-004

The Inspection Engine shall report total installed system memory.

---

### REQ-INS-005

The Inspection Engine shall enumerate all storage devices connected to the system.

---

### REQ-INS-006

The Inspection Engine shall identify storage device type.

Supported examples include:

* SATA HDD
* SATA SSD
* NVMe SSD
* USB Storage

---

### REQ-INS-007

The Inspection Engine shall retrieve SMART health information for supported storage devices.

---

### REQ-INS-008

The Inspection Engine shall report storage capacity and available free space.

---

### REQ-INS-009

The Inspection Engine shall enumerate all network adapters.

---

### REQ-INS-010

The Inspection Engine shall identify wired Ethernet interfaces.

---

### REQ-INS-011

The Inspection Engine shall detect wireless networking interfaces.

---

### REQ-INS-012

The Inspection Engine shall determine whether CPU virtualization support is available.

---

### REQ-INS-013

The Inspection Engine shall determine whether virtualization support is currently enabled within firmware.

---

### REQ-INS-014

The Inspection Engine shall detect UEFI firmware.

---

### REQ-INS-015

The Inspection Engine shall determine Secure Boot status.

---

### REQ-INS-016

The Inspection Engine shall retrieve system manufacturer information.

---

### REQ-INS-017

The Inspection Engine shall retrieve model information.

---

### REQ-INS-018

The Inspection Engine shall retrieve serial number information when available.

---

### REQ-INS-019

The Inspection Engine shall retrieve BIOS or firmware version information.

---

### REQ-INS-020

The Inspection Engine shall retrieve battery health information for supported portable systems.

---

### REQ-INS-021

The Inspection Engine shall determine whether battery charge threshold configuration is supported.

---

### REQ-INS-022

The Inspection Engine shall detect lid switch support on portable systems.

---

### REQ-INS-023

The Inspection Engine shall detect supported firmware management interfaces.

Examples include manufacturer-specific BIOS management capabilities.

---

### REQ-INS-024

The Inspection Engine shall verify Ethernet link status.

---

### REQ-INS-025

The Inspection Engine shall generate a hardware inspection report before any deployment workflow proceeds.

---

### REQ-INS-026

The Inspection Engine shall not modify firmware, storage devices, operating system settings, or user data during inspection.

---

### REQ-INS-027

Inspection results shall be made available to other Orion subsystems through documented interfaces.

---

### REQ-INS-028

Inspection results shall be retained for the duration of the deployment session.
