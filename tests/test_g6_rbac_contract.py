"""Non-destructive authorization regression using route-level dependency contracts."""
from fastapi.routing import APIRoute
from app.main import viewer_router, admin_router
from app.api.operations import router as operations_router
from app.auth.http import require_admin, require_authenticated, verify_csrf_token, verify_csrf_origin

def dependency_tree(dependencies):
    found=set()
    for dep in dependencies:
        if dep.call is not None:
            found.add(dep.call)
        found.update(dependency_tree(dep.dependencies))
    return found

def routes():
    result={}
    for router in (viewer_router,admin_router,operations_router):
        for route in router.routes:
            if isinstance(route,APIRoute):
                for method in route.methods:
                    result[(router.prefix+route.path,method)] = route
    return result

def test_viewer_read_apis_require_authentication():
    found=routes()
    for path in ('/api/dashboard','/api/settings','/api/engine-snapshots','/api/automation/status','/api/ops/logs'):
        route=found[(path,'GET')]
        deps=dependency_tree(route.dependant.dependencies)
        assert require_authenticated in deps, path

def test_admin_writes_enforce_role_and_csrf():
    found=routes()
    for path,method in (('/api/settings','PUT'),('/api/database/reset','POST')):
        deps=dependency_tree(found[(path,method)].dependant.dependencies)
        assert require_admin in deps, path
        assert verify_csrf_token in deps, path
        assert verify_csrf_origin in deps, path

def test_viewer_does_not_have_admin_write_binding():
    found=routes()
    assert ('/api/settings','PUT') in found
    assert require_admin in dependency_tree(found[('/api/settings','PUT')].dependant.dependencies)
    assert ('/api/database/reset','GET') not in found
