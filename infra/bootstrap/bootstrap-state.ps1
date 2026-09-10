[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string] $SubscriptionId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string] $TenantId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]{3,24}$')]
    [string] $StorageAccountName,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string] $BootstrapPrincipalObjectId,

    [ValidateSet('User', 'ServicePrincipal')]
    [string] $BootstrapPrincipalType = 'User',

    [string] $ResourceGroupName = 'zeroops-tfstate-rg',
    [string] $Location = 'centralindia',
    [string] $StateContainerName = 'platform-tfstate',
    [string] $PlanContainerName = 'deployment-plans'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

function Invoke-AzureCli {
    param([Parameter(Mandatory = $true)][string[]] $Arguments)

    $result = & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI failed: az $($Arguments -join ' ')"
    }
    return $result
}

function Invoke-AzureRestJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string]$Body
    )

    # Passing JSON inline through the Windows az.cmd shim strips the quotation
    # marks in some PowerShell configurations.  Supply a UTF-8 JSON file so ARM
    # receives an unmodified request body.
    $bodyPath = Join-Path ([System.IO.Path]::GetTempPath()) ("zeroops-azure-rest-{0}.json" -f [Guid]::NewGuid().ToString('N'))
    try {
        [System.IO.File]::WriteAllText($bodyPath, $Body, [System.Text.UTF8Encoding]::new($false))
        Invoke-AzureCli @(
            'rest', '--method', $Method,
            '--url', $Url,
            '--headers', 'Content-Type=application/json',
            '--body', ("@{0}" -f $bodyPath),
            '--output', 'none'
        ) | Out-Null
    }
    finally {
        if (Test-Path -LiteralPath $bodyPath) {
            Remove-Item -LiteralPath $bodyPath -Force -ErrorAction SilentlyContinue
        }
    }
}

$account = Invoke-AzureCli @('account', 'show', '--output', 'json') | ConvertFrom-Json
if ($account.state -ne 'Enabled' -or $account.id -ne $SubscriptionId -or $account.tenantId -ne $TenantId) {
    throw 'The active Azure CLI subscription or tenant does not match the explicit bootstrap target.'
}

foreach ($provider in @('Microsoft.Authorization', 'Microsoft.ManagedIdentity', 'Microsoft.Storage')) {
    $state = Invoke-AzureCli @('provider', 'show', '--namespace', $provider, '--query', 'registrationState', '--output', 'tsv')
    if ($state.Trim() -ne 'Registered') {
        throw "$provider is not registered. This script never registers providers implicitly."
    }
}

$groupExists = (& az group exists --name $ResourceGroupName --output tsv).Trim() -eq 'true'
if (-not $groupExists) {
    if ($PSCmdlet.ShouldProcess($ResourceGroupName, 'Create remote-state resource group')) {
        Invoke-AzureCli @(
            'group', 'create', '--name', $ResourceGroupName, '--location', $Location,
            '--tags', 'application=ZeroOps AI', 'managed-by=bootstrap', 'workload=terraform-state',
            '--output', 'none'
        ) | Out-Null
    }
}

# A missing account is the expected first-run case.  The script otherwise uses
# strict native-command error handling, so temporarily opt out only for this
# intentional existence probe and preserve the exit code for the create path.
$previousNativeCommandPreference = $PSNativeCommandUseErrorActionPreference
$PSNativeCommandUseErrorActionPreference = $false
try {
    $storageJson = & az storage account show --name $StorageAccountName --resource-group $ResourceGroupName --output json 2>$null
    $storageShowExitCode = $LASTEXITCODE
}
finally {
    $PSNativeCommandUseErrorActionPreference = $previousNativeCommandPreference
}
if ($storageShowExitCode -ne 0) {
    if ($PSCmdlet.ShouldProcess($StorageAccountName, 'Create hardened remote-state storage account')) {
        Invoke-AzureCli @(
            'storage', 'account', 'create',
            '--name', $StorageAccountName,
            '--resource-group', $ResourceGroupName,
            '--location', $Location,
            '--kind', 'StorageV2',
            '--sku', 'Standard_LRS',
            '--https-only', 'true',
            '--min-tls-version', 'TLS1_2',
            '--allow-blob-public-access', 'false',
            '--allow-shared-key-access', 'false',
            '--allow-cross-tenant-replication', 'false',
            '--default-action', 'Allow',
            '--public-network-access', 'Enabled',
            '--require-infrastructure-encryption', 'true',
            '--tags', 'application=ZeroOps AI', 'managed-by=bootstrap', 'workload=terraform-state',
            '--output', 'none'
        ) | Out-Null
    }
    $storageJson = Invoke-AzureCli @('storage', 'account', 'show', '--name', $StorageAccountName, '--resource-group', $ResourceGroupName, '--output', 'json')
}

$storage = $storageJson | ConvertFrom-Json
if ($storage.location -ne $Location -or $storage.allowSharedKeyAccess -ne $false -or $storage.allowBlobPublicAccess -ne $false) {
    throw 'An existing state account does not satisfy the fixed location/shared-key/public-blob contract.'
}

$storageId = $storage.id
foreach ($container in @($StateContainerName, $PlanContainerName)) {
    $containerUrl = "https://management.azure.com${storageId}/blobServices/default/containers/${container}?api-version=2023-05-01"
    # A private container is also absent on the first run.  Do not let the
    # script-wide native-command preference turn that intentional probe into a
    # terminating error before the create branch can run.
    $previousNativeCommandPreference = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        & az rest --method get --url $containerUrl --output none 2>$null
        $containerShowExitCode = $LASTEXITCODE
    }
    finally {
        $PSNativeCommandUseErrorActionPreference = $previousNativeCommandPreference
    }
    $exists = $containerShowExitCode -eq 0
    if (-not $exists -and $PSCmdlet.ShouldProcess($container, 'Create private Blob container')) {
        Invoke-AzureRestJson -Method 'put' -Url $containerUrl -Body '{"properties":{"publicAccess":"None"}}'
    }
}

if ($PSCmdlet.ShouldProcess($StorageAccountName, 'Enable state versioning and retention')) {
    Invoke-AzureCli @(
        'storage', 'account', 'blob-service-properties', 'update',
        '--account-name', $StorageAccountName,
        '--resource-group', $ResourceGroupName,
        '--enable-versioning', 'true',
        '--enable-delete-retention', 'true',
        '--delete-retention-days', '30',
        '--enable-container-delete-retention', 'true',
        '--container-delete-retention-days', '30',
        '--output', 'none'
    ) | Out-Null

    $policyUrl = "https://management.azure.com${storageId}/managementPolicies/default?api-version=2023-05-01"
    $policy = @{
        properties = @{
            policy = @{
                rules = @(
                    @{
                        enabled = $true
                        name = 'expire-saved-deployment-plans'
                        type = 'Lifecycle'
                        definition = @{
                            actions = @{ baseBlob = @{ delete = @{ daysAfterModificationGreaterThan = 2 } } }
                            filters = @{ blobTypes = @('blockBlob'); prefixMatch = @("${PlanContainerName}/plans/") }
                        }
                    }
                )
            }
        }
    } | ConvertTo-Json -Depth 12 -Compress
    Invoke-AzureRestJson -Method 'put' -Url $policyUrl -Body $policy
}

$blobContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
$existingAssignment = Invoke-AzureCli @(
    'role', 'assignment', 'list',
    '--assignee-object-id', $BootstrapPrincipalObjectId,
    '--scope', $storageId,
    '--role', $blobContributorRole,
    '--query', '[0].id',
    '--output', 'tsv'
)
if ([string]::IsNullOrWhiteSpace($existingAssignment) -and $PSCmdlet.ShouldProcess($BootstrapPrincipalObjectId, 'Grant bootstrap operator Blob Data Contributor on the state account')) {
    Invoke-AzureCli @(
        'role', 'assignment', 'create',
        '--assignee-object-id', $BootstrapPrincipalObjectId,
        '--assignee-principal-type', $BootstrapPrincipalType,
        '--role', $blobContributorRole,
        '--scope', $storageId,
        '--output', 'none'
    ) | Out-Null
}

[pscustomobject]@{
    resource_group_name  = $ResourceGroupName
    storage_account_name = $StorageAccountName
    state_container_name = $StateContainerName
    plan_container_name  = $PlanContainerName
    authentication       = 'Microsoft Entra ID only; shared keys disabled'
} | Format-List
