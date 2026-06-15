# SPDX-License-Identifier: Apache-2.0

"""
Ansible MCP Server - Tool Registration

Imports all tool modules to register their @mcp.tool() decorators.
"""

from . import (
    ad_hoc as ad_hoc,
)
from . import (
    credentials as credentials,
)
from . import (
    execution_environments as execution_environments,
)
from . import (
    groups as groups,
)
from . import (
    hosts as hosts,
)
from . import (
    instances as instances,
)
from . import (
    inventories as inventories,
)
from . import (
    job_templates as job_templates,
)
from . import (
    jobs as jobs,
)
from . import (
    labels as labels,
)
from . import (
    notifications as notifications,
)
from . import (
    organizations as organizations,
)
from . import (
    projects as projects,
)
from . import (
    rbac as rbac,
)
from . import (
    schedules as schedules,
)
from . import (
    system as system,
)
from . import (
    teams as teams,
)
from . import (
    users as users,
)
from . import (
    workflow_jobs as workflow_jobs,
)
from . import (
    workflow_templates as workflow_templates,
)
