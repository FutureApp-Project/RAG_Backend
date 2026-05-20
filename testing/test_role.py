import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.config.database.database import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.role import RoleEnum
import json

client = TestClient(app)

# Test data
ADMIN_CREDENTIALS = {
    "username": "Eckhard",
    "password": "Eckhard123"
}

PATIENT_CREDENTIALS = {
    "username": "patient123",
    "password": "patient123"
}

# Global variables to store tokens and created IDs
admin_token = None
patient_token = None
created_role_id = None


def get_auth_headers(token):
    """Helper function to get authorization headers"""
    return {"Authorization": f"Bearer {token}"}


def setup_module(module):
    """Setup before all tests"""
    global admin_token, patient_token
    
    # Login as admin
    response = client.post("/auth/login", data=ADMIN_CREDENTIALS)
    assert response.status_code == 200
    admin_token = response.json()["access_token"]
    
    # Login as patient
    response = client.post("/auth/login", data=PATIENT_CREDENTIALS)
    assert response.status_code == 200
    patient_token = response.json()["access_token"]


def test_1_admin_can_get_all_roles():
    """Test that admin can get all roles"""
    response = client.get("/roles/", headers=get_auth_headers(admin_token))
    assert response.status_code == 200
    roles = response.json()
    assert isinstance(roles, list)
    print(f"Admin retrieved {len(roles)} roles")


def test_2_patient_cannot_get_all_roles():
    """Test that patient cannot get all roles (403 Forbidden)"""
    response = client.get("/roles/", headers=get_auth_headers(patient_token))
    assert response.status_code == 403
    error_detail = response.json()["detail"]
    assert "insufficient permissions" in error_detail.lower() or "admin access required" in error_detail.lower()
    print("Patient correctly denied access to roles")


def test_3_admin_can_create_role():
    """Test that admin can create a new role"""
    global created_role_id
    
    new_role = {
        "role": "testrole",
        "is_active": True
    }
    
    response = client.post(
        "/roles/",
        json=new_role,
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 201
    role_data = response.json()
    assert role_data["role"] == "testrole"
    assert role_data["is_active"] == True
    created_role_id = role_data["id"]
    print(f"Admin created role 'testrole' with ID: {created_role_id}")


def test_4_duplicate_role_creation_fails():
    """Test that creating duplicate role fails"""
    duplicate_role = {
        "role": "testrole",  # Same as above
        "is_active": True
    }
    
    response = client.post(
        "/roles/",
        json=duplicate_role,
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 400
    error_detail = response.json()["detail"]
    assert "already exists" in error_detail.lower()
    print("Correctly prevented duplicate role creation")


def test_5_admin_can_get_role_by_id():
    """Test that admin can get role by ID"""
    response = client.get(
        f"/roles/{created_role_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 200
    role_data = response.json()
    assert role_data["id"] == created_role_id
    assert role_data["role"] == "testrole"
    print(f"Admin retrieved role by ID: {created_role_id}")


def test_6_patient_cannot_get_role_by_id():
    """Test that patient cannot get role by ID"""
    response = client.get(
        f"/roles/{created_role_id}",
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied access to specific role")


def test_7_admin_can_update_role():
    """Test that admin can update a role"""
    update_data = {
        "role": "testrole_updated",
        "is_active": False
    }
    
    response = client.put(
        f"/roles/{created_role_id}",
        json=update_data,
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 200
    role_data = response.json()
    assert role_data["role"] == "testrole_updated"
    assert role_data["is_active"] == False
    print(f"Admin updated role to: {role_data['role']}")


def test_8_cannot_update_system_roles():
    """Test that system roles (admin, bot) cannot be updated"""
    # First, we need to find admin role ID
    response = client.get("/roles/", headers=get_auth_headers(admin_token))
    roles = response.json()
    admin_role = next((r for r in roles if r["role"] == "admin"), None)
    
    if admin_role:
        update_data = {"role": "admin_updated"}
        response = client.put(
            f"/roles/{admin_role['id']}",
            json=update_data,
            headers=get_auth_headers(admin_token)
        )
        
        assert response.status_code == 403
        error_detail = response.json()["detail"]
        assert "cannot modify system roles" in error_detail.lower()
        print("Correctly prevented updating admin role")


def test_9_patient_cannot_update_role():
    """Test that patient cannot update a role"""
    update_data = {
        "role": "patient_trying_to_update",
        "is_active": True
    }
    
    response = client.put(
        f"/roles/{created_role_id}",
        json=update_data,
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied permission to update role")


def test_10_admin_can_delete_role():
    """Test that admin can delete a role (soft delete)"""
    response = client.delete(
        f"/roles/{created_role_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 204
    print(f"Admin soft-deleted role ID: {created_role_id}")
    
    # Verify the role is deleted (should return 404)
    response = client.get(
        f"/roles/{created_role_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 404
    print("Verified role is deleted (returns 404)")


def test_11_cannot_delete_system_roles():
    """Test that system roles cannot be deleted"""
    # Get admin role
    response = client.get("/roles/", headers=get_auth_headers(admin_token))
    roles = response.json()
    admin_role = next((r for r in roles if r["role"] == "admin"), None)
    
    if admin_role:
        response = client.delete(
            f"/roles/{admin_role['id']}",
            headers=get_auth_headers(admin_token)
        )
        
        assert response.status_code == 400
        error_detail = response.json()["detail"]
        assert "cannot delete system roles" in error_detail.lower()
        print("Correctly prevented deleting admin role")


def test_12_patient_cannot_delete_role():
    """Test that patient cannot delete a role"""
    # Create another role to test deletion
    new_role = {
        "role": "temp_role_for_deletion_test",
        "is_active": True
    }
    
    response = client.post(
        "/roles/",
        json=new_role,
        headers=get_auth_headers(admin_token)
    )
    assert response.status_code == 201
    temp_role_id = response.json()["id"]
    
    # Try to delete as patient
    response = client.delete(
        f"/roles/{temp_role_id}",
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied permission to delete role")
    
    # Clean up: delete as admin
    response = client.delete(
        f"/roles/{temp_role_id}",
        headers=get_auth_headers(admin_token)
    )
    assert response.status_code == 204


def test_13_create_role_with_invalid_data():
    """Test creating role with invalid data"""
    invalid_roles = [
        {},  # Empty data
        {"role": ""},  # Empty role name
        {"role": "a" * 21},  # Too long role name (if limited to 20 chars)
    ]
    
    for invalid_role in invalid_roles:
        response = client.post(
            "/roles/",
            json=invalid_role,
            headers=get_auth_headers(admin_token)
        )
        
        # Should return 422 (validation error) or 400
        assert response.status_code in [400, 422]
        print(f"Correctly rejected invalid role data: {invalid_role}")


if __name__ == "__main__":
    # Run tests sequentially
    setup_module(None)
    
    tests = [
        test_1_admin_can_get_all_roles,
        test_2_patient_cannot_get_all_roles,
        test_3_admin_can_create_role,
        test_4_duplicate_role_creation_fails,
        test_5_admin_can_get_role_by_id,
        test_6_patient_cannot_get_role_by_id,
        test_7_admin_can_update_role,
        test_8_cannot_update_system_roles,
        test_9_patient_cannot_update_role,
        test_10_admin_can_delete_role,
        test_11_cannot_delete_system_roles,
        test_12_patient_cannot_delete_role,
        test_13_create_role_with_invalid_data,
    ]
    
    for i, test in enumerate(tests, 1):
        print(f"\n{'='*60}")
        print(f"Running test {i}: {test.__name__}")
        print('='*60)
        try:
            test()
            print(f"✓ Test {i} passed")
        except Exception as e:
            print(f"✗ Test {i} failed: {str(e)}")
    
    print(f"\n{'='*60}")
    print("All tests completed!")
    print('='*60)