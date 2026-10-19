param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$Namespace,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$')]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'
if ($Tag -eq 'latest') { throw 'Use a unique release tag, not latest.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $images = @(
        @{ Name = 'api'; Context = '.'; File = 'Dockerfile.api' },
        @{ Name = 'frontend'; Context = 'frontend'; File = 'frontend/Dockerfile' },
        @{ Name = 'reranker'; Context = '.'; File = 'Dockerfile.reranker' }
    )
    # Build every image before uploading any part of the release.
    foreach ($item in $images) {
        $reference = "docker.io/${Namespace}/taxguide-$($item.Name):${Tag}"
        docker buildx build --platform linux/amd64 --load --label "org.opencontainers.image.version=${Tag}" --file $item.File --tag $reference $item.Context
        if ($LASTEXITCODE -ne 0) { throw "Build failed: $reference" }
    }
    foreach ($item in $images) {
        $reference = "docker.io/${Namespace}/taxguide-$($item.Name):${Tag}"
        docker push $reference
        if ($LASTEXITCODE -ne 0) { throw "Push failed: $reference. Release is incomplete; do not deploy it." }
        docker buildx imagetools inspect $reference
        if ($LASTEXITCODE -ne 0) { throw "Published manifest verification failed: $reference" }
    }
    $releaseDirectory = Join-Path $projectRoot "dist/demo-${Tag}"
    New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
    Copy-Item -LiteralPath 'compose.demo.yaml' -Destination $releaseDirectory
    $template = Get-Content -Raw '.env.demo.example'
    $template = $template.Replace('TAXGUIDE_IMAGE_NAMESPACE=', "TAXGUIDE_IMAGE_NAMESPACE=${Namespace}")
    $template = $template.Replace('TAXGUIDE_IMAGE_TAG=', "TAXGUIDE_IMAGE_TAG=${Tag}")
    Set-Content -LiteralPath (Join-Path $releaseDirectory '.env.demo.example') -Value $template -Encoding utf8
    Copy-Item -LiteralPath 'docs/image-deployment.md' -Destination (Join-Path $releaseDirectory 'README.md')
    Copy-Item -LiteralPath 'docs/single-host-deployment.md' -Destination $releaseDirectory
    Write-Output "Published all three images. VM deployment files: $releaseDirectory"
}
finally {
    Pop-Location
}
