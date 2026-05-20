import pytest
from fastapi.testclient import TestClient
from app.main import app
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

# Global variables
admin_token = None
patient_token = None
created_menu_id = None
test_role_id = None  # We'll get a role ID to associate with menu


def get_auth_headers(token):
    """Helper function to get authorization headers"""
    return {"Authorization": f"Bearer {token}"}


def setup_module(module):
    """Setup before all tests"""
    global admin_token, patient_token, test_role_id
    
    # Login as admin
    response = client.post("/auth/login", data=ADMIN_CREDENTIALS)
    assert response.status_code == 200
    admin_token = response.json()["access_token"]
    
    # Login as patient
    response = client.post("/auth/login", data=PATIENT_CREDENTIALS)
    assert response.status_code == 200
    patient_token = response.json()["access_token"]
    
    # Get a role ID to use in menu tests (use patient role)
    response = client.get("/roles/", headers=get_auth_headers(admin_token))
    roles = response.json()
    patient_role = next((r for r in roles if r["role"] == "patient"), None)
    if patient_role:
        test_role_id = patient_role["id"]
        print(f"Using patient role ID: {test_role_id}")


def test_1_admin_can_get_all_menu_items():
    """Test that admin can get all menu items"""
    response = client.get("/menu/", headers=get_auth_headers(admin_token))
    assert response.status_code == 200
    menu_items = response.json()
    assert isinstance(menu_items, list)
    print(f"Admin retrieved {len(menu_items)} menu items")


def test_2_patient_cannot_get_all_menu_items():
    """Test that patient cannot get all menu items"""
    response = client.get("/menu/", headers=get_auth_headers(patient_token))
    assert response.status_code == 403
    error_detail = response.json()["detail"]
    assert "insufficient permissions" in error_detail.lower() or "admin access required" in error_detail.lower()
    print("Patient correctly denied access to all menu items")


def test_3_admin_can_create_menu_item():
    """Test that admin can create a new menu item"""
    global created_menu_id
    
    new_menu_item = {
        "text": "Test Menu Item",
        "route": "/test-route",
        "icon": "test-icon",
        "item_order": 99,
        "role_ids": [test_role_id] if test_role_id else []
    }
    
    response = client.post(
        "/menu/",
        json=new_menu_item,
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 201
    menu_data = response.json()
    assert menu_data["text"] == "Test Menu Item"
    assert menu_data["route"] == "/test-route"
    assert menu_data["icon"] == "test-icon"
    assert menu_data["item_order"] == 99
    created_menu_id = menu_data["id"]
    print(f"Admin created menu item with ID: {created_menu_id}")


def test_4_duplicate_menu_item_creation_fails():
    """Test that creating duplicate menu item fails"""
    duplicate_menu = {
        "text": "Test Menu Item",  # Same text
        "route": "/different-route",
        "icon": "different-icon",
        "item_order": 100,
        "role_ids": []
    }
    
    response = client.post(
        "/menu/",
        json=duplicate_menu,
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 400
    error_detail = response.json()["detail"]
    assert "already exists" in error_detail.lower()
    print("Correctly prevented duplicate menu item creation")


def test_5_admin_can_get_menu_item_by_id():
    """Test that admin can get menu item by ID"""
    response = client.get(
        f"/menu/{created_menu_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 200
    menu_data = response.json()
    assert menu_data["id"] == created_menu_id
    assert menu_data["text"] == "Test Menu Item"
    print(f"Admin retrieved menu item by ID: {created_menu_id}")


def test_6_patient_cannot_get_menu_item_by_id():
    """Test that patient cannot get menu item by ID"""
    response = client.get(
        f"/menu/{created_menu_id}",
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied access to specific menu item")


def test_7_admin_can_update_menu_item():
    """Test that admin can update a menu item"""
    update_data = {
        "text": "Updated Test Menu Item",
        "route": "/updated-route",
        "icon": "updated-icon",
        "item_order": 50
    }
    
    response = client.put(
        f"/menu/{created_menu_id}",
        json=update_data,
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 200
    menu_data = response.json()
    assert menu_data["text"] == "Updated Test Menu Item"
    assert menu_data["route"] == "/updated-route"
    assert menu_data["icon"] == "updated-icon"
    assert menu_data["item_order"] == 50
    print(f"Admin updated menu item to: {menu_data['text']}")


def test_8_admin_can_update_menu_roles():
    """Test that admin can update roles for a menu item"""
    if not test_role_id:
        print("Skipping role update test - no role ID available")
        return
    
    # Get doctor role ID
    response = client.get("/roles/", headers=get_auth_headers(admin_token))
    roles = response.json()
    doctor_role = next((r for r in roles if r["role"] == "doctor"), None)
    
    if doctor_role:
        # Update with both patient and doctor roles
        role_ids = [test_role_id, doctor_role["id"]]
        
        response = client.put(
            f"/menu/{created_menu_id}/roles",
            json=role_ids,
            headers=get_auth_headers(admin_token)
        )
        
        assert response.status_code == 200
        menu_data = response.json()
        assert len(menu_data.get("roles", [])) >= 2
        role_names = [r["role"] for r in menu_data.get("roles", [])]
        assert "patient" in role_names
        assert "doctor" in role_names
        print(f"Updated menu item roles: {role_names}")


def test_9_patient_cannot_update_menu_item():
    """Test that patient cannot update a menu item"""
    update_data = {
        "text": "Patient Trying to Update",
        "route": "/patient-route"
    }
    
    response = client.put(
        f"/menu/{created_menu_id}",
        json=update_data,
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied permission to update menu item")


def test_10_patient_cannot_update_menu_roles():
    """Test that patient cannot update menu roles"""
    if not test_role_id:
        print("Skipping role update test - no role ID available")
        return
    
    response = client.put(
        f"/menu/{created_menu_id}/roles",
        json=[test_role_id],
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied permission to update menu roles")


def test_11_admin_can_get_menu_items_by_role():
    """Test that admin can get menu items by role ID"""
    if not test_role_id:
        print("Skipping test - no role ID available")
        return
    
    response = client.get(
        f"/menu/role/{test_role_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 200
    menu_items = response.json()
    assert isinstance(menu_items, list)
    # Our test menu item should be in the list since we assigned patient role to it
    test_items = [item for item in menu_items if item["text"] == "Updated Test Menu Item"]
    assert len(test_items) > 0
    print(f"Admin retrieved {len(menu_items)} menu items for role ID {test_role_id}")


def test_12_patient_cannot_get_menu_items_by_role():
    """Test that patient cannot get menu items by role ID"""
    if not test_role_id:
        print("Skipping test - no role ID available")
        return
    
    response = client.get(
        f"/menu/role/{test_role_id}",
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied access to menu items by role")


def test_13_admin_can_delete_menu_item():
    """Test that admin can delete a menu item (soft delete)"""
    # First create another menu item to delete
    temp_menu = {
        "text": "Temp Menu Item for Deletion",
        "route": "/temp-route",
        "item_order": 999
    }
    
    response = client.post(
        "/menu/",
        json=temp_menu,
        headers=get_auth_headers(admin_token)
    )
    assert response.status_code == 201
    temp_menu_id = response.json()["id"]
    
    # Delete it
    response = client.delete(
        f"/menu/{temp_menu_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 204
    print(f"Admin soft-deleted menu item ID: {temp_menu_id}")
    
    # Verify it's deleted (should return 404)
    response = client.get(
        f"/menu/{temp_menu_id}",
        headers=get_auth_headers(admin_token)
    )
    
    assert response.status_code == 404
    print("Verified menu item is deleted (returns 404)")


def test_14_patient_cannot_delete_menu_item():
    """Test that patient cannot delete a menu item"""
    # Create a menu item to test deletion
    temp_menu = {
        "text": "Menu Item for Patient Deletion Test",
        "route": "/patient-test",
        "item_order": 888
    }
    
    response = client.post(
        "/menu/",
        json=temp_menu,
        headers=get_auth_headers(admin_token)
    )
    assert response.status_code == 201
    temp_menu_id = response.json()["id"]
    
    # Try to delete as patient
    response = client.delete(
        f"/menu/{temp_menu_id}",
        headers=get_auth_headers(patient_token)
    )
    
    assert response.status_code == 403
    print("Patient correctly denied permission to delete menu item")
    
    # Clean up: delete as admin
    response = client.delete(
        f"/menu/{temp_menu_id}",
        headers=get_auth_headers(admin_token)
    )
    assert response.status_code == 204


def test_15_create_menu_item_with_invalid_data():
    """Test creating menu item with invalid data"""
    invalid_menus = [
        {},  # Empty data
        {"text": ""},  # Empty text
        {"text": "   "},  # Whitespace only text
        {"text": "a" * 256},  # Too long text (max 255)
        {"text": "Valid", "item_order": -1},  # Negative order
    ]
    
    for i, invalid_menu in enumerate(invalid_menus):
        response = client.post(
            "/menu/",
            json=invalid_menu,
            headers=get_auth_headers(admin_token)
        )
        
        # Should return 422 (validation error) or 400
        assert response.status_code in [400, 422]
        print(f"Correctly rejected invalid menu data {i+1}: {invalid_menu}")


def test_16_cleanup_test_menu_item():
    """Clean up the test menu item created earlier"""
    if created_menu_id:
        response = client.delete(
            f"/menu/{created_menu_id}",
            headers=get_auth_headers(admin_token)
        )
        
        # Should be 204 or 404 (if already deleted)
        assert response.status_code in [204, 404]
        print(f"Cleaned up test menu item ID: {created_menu_id}")


if __name__ == "__main__":
    # Run tests sequentially
    setup_module(None)
    
    tests = [
        test_1_admin_can_get_all_menu_items,
        test_2_patient_cannot_get_all_menu_items,
        test_3_admin_can_create_menu_item,
        test_4_duplicate_menu_item_creation_fails,
        test_5_admin_can_get_menu_item_by_id,
        test_6_patient_cannot_get_menu_item_by_id,
        test_7_admin_can_update_menu_item,
        test_8_admin_can_update_menu_roles,
        test_9_patient_cannot_update_menu_item,
        test_10_patient_cannot_update_menu_roles,
        test_11_admin_can_get_menu_items_by_role,
        test_12_patient_cannot_get_menu_items_by_role,
        test_13_admin_can_delete_menu_item,
        test_14_patient_cannot_delete_menu_item,
        test_15_create_menu_item_with_invalid_data,
        test_16_cleanup_test_menu_item,
    ]
    
    for i, test in enumerate(tests, 1):
        print(f"\n{'='*60}")
        print(f"Running test {i}: {test.__name__}")
        print('='*60)
        try:
            test()
            print(f"✓ Test {i} passed")
        except AssertionError as e:
            print(f"✗ Test {i} failed (AssertionError): {str(e)}")
        except Exception as e:
            print(f"✗ Test {i} failed (Exception): {str(e)}")
    
    print(f"\n{'='*60}")
    print("All menu tests completed!")
    print('='*60)