# -*- coding: utf-8 -*-

import json
import requests
import tempfile
from os.path import basename, join
from os import remove as remove_file
from time import sleep
from typing import Callable, Dict
import arcpy
from arcgis.features import FeatureLayer


HOST = "https://api.celantur.com/v2"
PREDEFINED_TILING = [
    "pano:4096",
    "pano:5400",
    "pano:5640",
    "pano:7060",
    "pano:7680",
    "pano:8000",
    "pano:7680",
    "pano:8000",
    "pano:8192",
    "pano:11000",
    "whole",
]


class CelanturAPIClient:
    STORE_OUTPUT_FOLDER = tempfile.gettempdir()
    SUPPORTED_CONTENT_TYES = ("image/jpeg", "image/png")
    FEATURE_LAYER_FLAG_NAME = "new_anonymized"
    MAX_ITERATIONS_BEFORE_REAUTH = 10

    def __init__(
        self,
        username: str,
        password: str,
        parameters: dict,
        remove_original_image: bool,
        std_out: Callable[[str], None],
        err_out: Callable[[str], None],
    ) -> None:
        self.std_out = std_out
        self.err_out = err_out
        self.parameters = parameters
        self.remove_original_image = remove_original_image
        self._username = username
        self._password = password
        self.iterations_before_reauth = self.MAX_ITERATIONS_BEFORE_REAUTH + 1
        self.auth_token: str = None

    def connect(self, force: bool = False) -> Dict[str, str]:
        """
        Get access token for Celantur Cloud API
        """
        payload = {
            "username": self._username,
            "password": self._password,
        }
        try:
            if (
                force
                or self.auth_token is None
                or self.iterations_before_reauth >= self.MAX_ITERATIONS_BEFORE_REAUTH
            ):
                response = requests.post(f"{HOST}/signin", json=payload, timeout=30)
                token = response.json()["AccessToken"]
                self.std_out(
                    f"User {self._username} successfully authenticated and token received."
                )
                self.auth_token = {"Authorization": token}
                self.iterations_before_reauth = 0
            else:
                self.std_out(
                    f"Iteration before next authentication: {self.iterations_before_reauth} / {self.MAX_ITERATIONS_BEFORE_REAUTH}"
                )
                self.iterations_before_reauth += 1
            return self.auth_token
        except requests.exceptions.ConnectionError as e:
            self.err_out(f"Authentication Error: Failed to connect to the {HOST}.")
            raise e
        except requests.exceptions.Timeout as e:
            self.err_out(f"Authentication Error: Request to {HOST} timed out.")
            raise e
        except requests.exceptions.RequestException as e:
            self.err_out(f"Authentication Error: HTTP error occurred: {e}")
            raise e
        except (ValueError, KeyError) as e:
            self.err_out(f"Authentication Error: Failed to parse response from {HOST}.")
            raise e
        except Exception as e:
            self.err_out(f"Authentication Error: An unexpected error occurred: {e}")
            raise e

    def start_anonymisation(self, *files: str) -> Dict[str, str]:
        """
        Upload file to Celantur Cloud API
        """
        res = {}
        for file in files:
            response = requests.post(
                f"{HOST}/task",
                json=self.parameters,
                headers=self.auth_token,
                timeout=30,
            )
            if response.status_code == 200:
                result = response.json()
                task_id = result["task_id"]
                upload_url = result["upload_url"]
                with open(file, "rb") as fd:
                    file_content = fd.read()
                requests.put(upload_url, data=file_content, timeout=30)
                res[task_id] = file
                self.std_out(
                    f"Image {file} uploaded with following parameters {self.parameters}. Waiting for processing..."
                )
            else:
                raise ValueError(
                    f"Cannot anonymise file {file} due to [{response.status_code}] {response.text} "
                )

        return res

    def finish_anonymisation(self, tasks: Dict[str, str]) -> Dict[str, str]:
        """
        Wait for processing to finish and download the anonymised file.
        """
        anon_files = {}
        for tid, file in tasks.items():
            keep_checking = True
            result = None
            while keep_checking:
                response = requests.get(
                    f"{HOST}/task/{tid}/status",
                    headers=self.auth_token,
                    timeout=30,
                )
                result = response.json()
                if result["task_status"] == "done":
                    self.std_out("Image is processed. Downloading...")
                    keep_checking = False
                elif result["task_status"] == "failed":
                    self.err_out(f"Processing of task {tid} failed")
                elif result["task_status"] == "processing":
                    self.std_out(
                        "Image is being processing. Waiting 5 seconds (polling)..."
                    )
                    sleep(5)
                else:
                    self.std_out("Waiting 5 seconds (polling)...")
                    sleep(5)

            file_name = basename(file)
            try:
                response = requests.get(result["anonymized_url"], timeout=30)
            except:
                self.err_out(
                    f"Error: Cannot finish anonymisation with following response: {result}"
                )
            final_name = join(self.STORE_OUTPUT_FOLDER, f"anon-{file_name}")
            with open(final_name, "wb") as fd:
                fd.write(response.content)
            anon_files["tid"] = final_name

        return anon_files

    def process_images(self, layer: str) -> None:
        """
        Blur images via Celantur Cloud API
        """
        self.std_out("Processing started...")

        # See https://developers.arcgis.com/python/latest/guide/working-with-feature-layers-and-features/#accessing-feature-layers-from-a-feature-layer-url
        layer = FeatureLayer(layer)

        available_attachments = layer.attachments.search()

        for attachment_object in available_attachments:

            featureset_id = attachment_object["PARENTOBJECTID"]
            attachment_content_type = attachment_object["CONTENTTYPE"]

            if attachment_content_type in self.SUPPORTED_CONTENT_TYES:
                featureset = layer.query(where=f"OBJECTID={featureset_id}")

                if not featureset:
                    continue

                all_features = featureset.features
                feature = all_features[0]

                is_anonymized = feature.attributes[self.FEATURE_LAYER_FLAG_NAME]

                if not is_anonymized:
                    attachment_id = attachment_object["ID"]
                    self.std_out(f"Anonymizing {attachment_object}\n")
                    local_path = layer.attachments.download(
                        oid=featureset_id, attachment_id=attachment_id
                    )
                    local_path = local_path[0]

                    self.connect()
                    tasks = self.start_anonymisation(local_path)
                    anon_files = self.finish_anonymisation(tasks)

                    for anon_file in anon_files.values():
                        layer.attachments.add(featureset_id, anon_file)
                        feature.attributes[self.FEATURE_LAYER_FLAG_NAME] = True
                        layer.edit_features(updates=[feature])
                        remove_file(anon_file)
                    if self.remove_original_image:
                        layer.attachments.delete(featureset_id, attachment_id)
                else:
                    self.std_out(f"Skipping (already anonymized) {attachment_object}\n")
            else:
                self.std_out(f"Skipping (non-image) {attachment_object}\n")

        self.std_out("Processing finished!")


class Toolbox:
    """Define the toolbox (the name of the toolbox is the name of the .pyt file)."""

    def __init__(self):
        self.label = "Celantur Blurring Toolbox"
        self.alias = "celanturblurringtoolbox"

        # List of tool classes associated with this toolbox
        self.tools = [Tool]


class Tool:
    """
    Define the tool (tool name is the name of the class).
    https://pro.arcgis.com/en/pro-app/latest/arcpy/geoprocessing_and_python/defining-parameters-in-a-python-toolbox.htm
    """

    def __init__(self):
        self.label = "Celantur Blurring Tool"
        self.description = "Tool to connect to Celantur Cloud API and blur images"
        self.params = []

    @classmethod
    def is_valid_json(cls, json_str: str) -> bool:
        try:
            json.loads(json_str)
            return True
        except ValueError:
            return False

    def getParameterInfo(self):
        """Define the tool parameters."""
        username = arcpy.Parameter(
            displayName="Celantur App username (email)",
            name="username",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            # category="CelanturAuth",
        )

        password = arcpy.Parameter(
            displayName="Celantur App password",
            name="password",
            datatype="GPStringHidden",
            parameterType="Required",
            direction="Input",
            # category="CelanturAuth",
        )

        blur_face = arcpy.Parameter(
            displayName="Blur faces",
            name="blur_face",
            datatype="GPBoolean",
            direction="Input",
            # category="AnonymisationParameters",
        )

        blur_license_plate = arcpy.Parameter(
            displayName="Blure license plates",
            name="blur_license_plate",
            datatype="GPBoolean",
            direction="Input",
            # category="AnonymisationParameters",
        )

        blur_person = arcpy.Parameter(
            displayName="Blur whole persons",
            name="blur_person",
            datatype="GPBoolean",
            direction="Input",
            # category="AnonymisationParameters",
        )

        blur_vehicle = arcpy.Parameter(
            displayName="Blur whole vehicles",
            name="blur_vehicle",
            datatype="GPBoolean",
            direction="Input",
            # category="AnonymisationParameters",
        )

        format_type = arcpy.Parameter(
            displayName="Format (tiling) type",
            name="format_type",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            # category="AnonymisationParameters",
        )

        format_value = arcpy.Parameter(
            displayName="Format value",
            name="format_value",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            # category="AnonymisationParameters",
        )

        jpeg_quality = arcpy.Parameter(
            displayName="JPEG quality",
            name="jpeg_quality",
            datatype="GPLong",
            parameterType="Required",
            direction="Input",
            # category="AnonymisationParameters",
        )

        remove_original_image = arcpy.Parameter(
            displayName="Remove original image",
            name="remove_original_image",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input",
        )

        layer = arcpy.Parameter(
            displayName="Feature Service Layer",
            name="feature_service_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )

        self.params = [
            username,
            password,
            blur_face,
            blur_license_plate,
            blur_person,
            blur_vehicle,
            format_type,
            format_value,
            jpeg_quality,
            remove_original_image,
            layer,
        ]

        self.initializeParameters(self.params)

        return self.params

    def initializeParameters(self, parameters):
        """Refine the properties of a tool's parameters. This method is
        called when the tool is opened."""

        self.blur_objects = {
            "face": parameters[2],
            "license-plate": parameters[3],
            "person": parameters[4],
            "vehicle": parameters[5],
        }

        self.format_type = parameters[6]
        self.format_value = parameters[7]
        self.jpeg_quality = parameters[8]
        self.remove_original_image = parameters[9]

        self.blur_objects["face"].value = True
        self.blur_objects["license-plate"].value = True
        self.blur_objects["person"].value = False
        self.blur_objects["vehicle"].value = False

        self.remove_original_image.value = False

        self.format_type.value = "pre-defined"
        self.format_type.filter.list = ["pre-defined", "self-defined"]

        self.format_value.value = "whole"

        self.jpeg_quality.value = 90
        self.jpeg_quality.filter.type = "Range"
        self.jpeg_quality.filter.list = [0, 100]

    def isLicensed(self):
        """Set whether the tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        self.format_type = parameters[6]
        self.format_value = parameters[7]
        self.format_value.value = self.format_value.value.strip()

        if self.format_type.value == "pre-defined":
            self.format_value.filter.list = PREDEFINED_TILING
        elif self.format_type.value == "self-defined":
            self.format_value.filter.list = []
        else:
            # self.format_type.setErrorMessage("Error: Please choose either 'pre-defined' or 'self-defined'.")
            pass

    def validate_parameters(self, parameters, messages):
        self.blur_objects = {
            "face": parameters[2],
            "license-plate": parameters[3],
            "person": parameters[4],
            "vehicle": parameters[5],
        }
        self.format_value = parameters[7]

        # Check that at least one object type is selected for blurring
        any_object_selected = any(o.value for o in self.blur_objects.values())
        if not any_object_selected:
            for o in self.blur_objects.values():
                # o.setErrorMessage("At least one object must be selected.")
                raise ValueError(
                    "At least one object (face, license-plate, person, vehicle) must be selected for blurring."
                )

        if (
            self.is_valid_json(self.format_value.value)
            or self.format_value.value in PREDEFINED_TILING
        ):
            messages.addMessage(f"Tiling format: {self.format_value.value}")
        else:
            # self.format_value.setErrorMessage("Wrong format. See https://doc.celantur.com/container/usage/batch-and-stream-mode#image-format")
            raise ValueError(
                f"'{self.format_value.value}' is not a correct tiling format."
                "See https://doc.celantur.com/container/usage/batch-and-stream-mode#image-format"
            )

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        username = parameters[0].value
        password = parameters[1].value

        anonym_parameters = {
            "face": parameters[2].value,
            "license-plate": parameters[3].value,
            "person": parameters[4].value,
            "vehicle": parameters[5].value,
            "format": parameters[7].value,
            "quality": parameters[8].value,
            "anonymization_method": "blur",
        }

        remove_original_image = parameters[9].value

        layer = parameters[10].value

        messages.addMessage(f"Username: {username}")
        messages.addMessage(f"Layer: {layer}")

        self.validate_parameters(parameters, messages)

        celantur = CelanturAPIClient(
            username,
            password,
            anonym_parameters,
            remove_original_image,
            messages.addMessage,
            messages.addErrorMessage,
        )

        celantur.process_images(str(layer))
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return


class ToolValidator(object):
    """Class for validating a tool's parameter values and controlling
    the behavior of the tool's dialog."""

    def __init__(self):
        """Setup arcpy and the list of tool parameters."""
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self):
        """Refine the properties of a tool's parameters. This method is
        called when the tool is opened."""

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""

    def updateMessages(self):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
