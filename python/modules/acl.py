# Check for changes
def check_changes(self, parent, compare_new, compare_old):
    # if request["parent"]["spec"]["name"] != request["parent"]["status"]["applied_acl_name"]:
    if compare_new != compare_old:
        # Remove ACL (also removes from interface)
        print("ACL CRD SPEC OUT OF SYNC! Removing and re-adding with new details! DETAILS: new value "+str(compare_new)+" does not match old value "+str(compare_old))
        fake_request = { "parent": { "spec": { "name": parent["status"]["applied_acl_name"], "interface": parent["status"]["applied_interface"]  } } }
        self.acl_finalize(fake_request)
        return True # Changes, ACL + WAN assignment removed
    else:
        print("ACL CRD spec has not changed since last sync. DETAILS: new value "+str(compare_new)+" matchs old value "+str(compare_old))
        return False # No changes

# Perform Sync
def acl_sync(self, request):
    import json

    print("ACL SYNC")
    acl_exists = False
    interface_acl_exists = False

    # Check if any of the spec parameters from the CRD have changed from the last applied status and try to delete the ACL if it has
    removed = False
    if "status" in request["parent"]:
        if "applied_acl_name" in request["parent"]["status"] and not removed: 
            removed = self.check_changes(request["parent"], request["parent"]["spec"]["name"], request["parent"]["status"]["applied_acl_name"])
        if "applied_interface" in request["parent"]["status"] and not removed:
            removed = self.check_changes(request["parent"], request["parent"]["spec"]["interface"], request["parent"]["status"]["applied_interface"])
        if "applied_sequence" in request["parent"]["status"] and not removed:
            removed = self.check_changes(request["parent"], request["parent"]["spec"]["sequence"], request["parent"]["status"]["applied_sequence"])


    # Get the existing ACLs
    get_existing = json.loads(self.tnsr_api_call("/data/netgate-acl:acl-config", "", "get", "json").text)

    # See if the ACL being synced is in the list already
    for i in get_existing["netgate-acl:acl-config"]["acl-table"]["acl-list"]:
        if i["acl-name"] == request["parent"]["spec"]["name"]:
            print(request["parent"]["spec"]["name"], "exists in TNSR.")
            acl_exists = True
            break

    # If not present, try to create it.
    if not acl_exists:
        payload = """
            <acl-list>
                <acl-name>"""+request["parent"]["spec"]["name"]+"""</acl-name>
                <acl-description>Automatically generated by tnsr-controller in Kubernetes</acl-description>
                <acl-rules>
                    <acl-rule>
                        <acl-rule-description>Default Generated Rule</acl-rule-description>
                        <sequence>1</sequence>
                        <action>permit</action>
                        <ip-version>ipv4</ip-version>
                        <protocol>icmp</protocol>
                    </acl-rule>
                </acl-rules>
            </acl-list>
        """
        create_acl = self.tnsr_api_call("/data/netgate-acl:acl-config/netgate-acl:acl-table", payload, "post", "xml")
        # DEBUG DUMP RESPONSE
        # print(create_acl.url)
        # print(create_acl.text)

        # Set the the acl_exists var to true so it is reflected in the Kubernetes resource
        if create_acl.status_code == 201 or create_acl.status_code == 409 :
            acl_exists = True

    # Get existing ACLs on Interface
    get_interface = json.loads(self.tnsr_api_call("/data/netgate-interface:interfaces-config/netgate-interface:interface="+request["parent"]["spec"]["interface"], "", "get", "json").text)
    # print(get_interface)

    # See if the ACL being synced is applied to the interface already
    if "access-list" in get_interface["netgate-interface:interface"][0]:
        for i in get_interface["netgate-interface:interface"][0]["access-list"]["input"]["acl-list"]:
            if i["acl-name"] == request["parent"]["spec"]["name"]:
                print(request["parent"]["spec"]["name"], "exists on interface "+request["parent"]["spec"]["interface"]+".")
                interface_acl_exists = True
                break
    # Return an error if the access list element isnt present on the interface, it (and the input chain) needs to be manually created first.
    else: 
        result = {
            "status": {
                "error": "Access list element does not exist for interface \""+request["parent"]["spec"]["interface"]+"\" in TNSR. Please create the access list element and input chain manually for before you can specify this interface."
            }
        }
        return result

    # If not present on the interface, try to create it.
    if not interface_acl_exists:
        payload = """
            <acl-list>
                <sequence>"""+str(request["parent"]["spec"]["sequence"])+"""</sequence>
                <acl-name>"""+request["parent"]["spec"]["name"]+"""</acl-name>
            </acl-list>
        """
        create_interface_acl = self.tnsr_api_call("/data/netgate-interface:interfaces-config/netgate-interface:interface=WAN/netgate-interface:access-list/netgate-interface:input", payload, "post", "xml")
        # # DEBUG DUMP RESPONSE
        # print(create_interface_acl.url)
        # print(create_interface_acl.text)

        # Set the the acl_exists var to true so it is reflected in the Kubernetes resource
        if create_interface_acl.status_code == 201 or create_interface_acl.status_code == 409:
                interface_acl_exists = True

    # Tell Kubernetes the status of the ACL on TNSR
    result = {
        "resyncAfterSeconds": 10, 
        "status": {
            "present": acl_exists,
            "applied": interface_acl_exists,
            "applied_interface": request["parent"]["spec"]["interface"],
            "applied_sequence": request["parent"]["spec"]["sequence"],
            "applied_acl_name": request["parent"]["spec"]["name"],
            "error": "none"
        }
    }
    return result


# Perform Deletion
def acl_finalize(self, request):
    import json

    print("ACL FINALIZE")
    finalized = False
    acl_exists = False
    interface_acl_exists = False

    # Get existing ACLs on Interface
    get_interface = json.loads(self.tnsr_api_call("/data/netgate-interface:interfaces-config/netgate-interface:interface="+request["parent"]["spec"]["interface"], "", "get", "json").text)
    # print(get_interface)

    # See if the ACL being finalized is applied to the interface
    for i in get_interface["netgate-interface:interface"][0]["access-list"]["input"]["acl-list"]:
        if i["acl-name"] == request["parent"]["spec"]["name"]:
            print(request["parent"]["spec"]["name"], "exists on interface "+request["parent"]["spec"]["interface"]+".")
            interface_acl_exists = True
            break

    # Get existing ACLs
    get_existing = json.loads(self.tnsr_api_call("/data/netgate-acl:acl-config", "", "get", "json").text)

    # Check if ACL exists
    for i in get_existing["netgate-acl:acl-config"]["acl-table"]["acl-list"]:
        if i["acl-name"] == request["parent"]["spec"]["name"]:
            print(request["parent"]["spec"]["name"], "exists in TNSR.")
            acl_exists = True
            break

    # If the ACL doesn't exist and isnt applied to the interface, we're done
    if not acl_exists and not interface_acl_exists:
        finalized = True
    # If the ACL does exist and/or is applied to the interface, we need to try and delete it
    else:
        if interface_acl_exists:
            delete_interface_acl = self.tnsr_api_call("/data/netgate-interface:interfaces-config/netgate-interface:interface="+request["parent"]["spec"]["interface"]+"/netgate-interface:access-list/netgate-interface:input/netgate-interface:acl-list="+request["parent"]["spec"]["name"], "", "delete", "json")
            # DEBUG DUMP RESPONSE
            # print(delete_interface_acl.text)

            # Set interface_acl_exists acl_exists false if successfully removed the ACL
            if delete_interface_acl.status_code == 204:
                interface_acl_exists = False
        if acl_exists:
            delete_acl = self.tnsr_api_call("/data/netgate-acl:acl-config/netgate-acl:acl-table/netgate-acl:acl-list="+request["parent"]["spec"]["name"], "", "delete", "json")
            # DEBUG DUMP RESPONSE
            # print(delete_acl.text)

            # Set acl_exists false if successfully removed the ACL
            if delete_acl.status_code == 204:
                acl_exists = False

        # Make sure everything is actually deleted
        if not acl_exists and not interface_acl_exists:
            finalized = True

    # Return the finalized status to Kubernetes
    result = {
        "finalized": finalized
    }
    return result