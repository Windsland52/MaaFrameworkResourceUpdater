import os
import json
import logging
from unidiff import PatchSet
from typing import Optional, Dict

import requests
from requests.models import Response
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s][%(levelname)s] %(message)s"
)


class MaaFrameworkUpdater:
    BASE_URL = "https://api.github.com"
    CHECK_TOKEN_VALIDITY_URL = BASE_URL + "/user"
    RELEASES_URL_TEMPLATE = BASE_URL + "/repos/{repo}/releases"
    COMPARE_URL_TEMPLATE = (
        BASE_URL + "/repos/{repo}/compare/{current_version}...{latest_version}"
    )
    DEFAULT_HEADERS = {"Accept": "application/vnd.github+json"}

    def __init__(
        self,
        base_dir: str = ".",
        diff_dir: str = "patch",
        prerelease: bool = False,
        token: str = "",
    ) -> None:
        """
        Initialize the MaaFrameworkUpdater.
        """
        self.base_dir = base_dir
        self.repo = None
        self.prerelease = prerelease
        self.current_version = None
        self.latest_version = None
        self.diff_dir = diff_dir
        self.diff_filename = "current_latest.diff"
        self.headers = self.DEFAULT_HEADERS.copy()
        if token:
            self.headers["Authorization"] = "Bearer " + token

        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, self.diff_dir), exist_ok=True)

    def read_interface(self) -> bool:
        """
        Read the interface file to get the current version and repository name.
        """
        try:
            with open(
                os.path.join(self.base_dir, "interface.json"), "r", encoding="utf-8"
            ) as file:
                data = json.load(file)
            self.current_version = data["version"]
            self.repo = "/".join(data["url"].split("/")[-2:])
            return True
        except FileNotFoundError:
            logging.error("interface.json file not found.")
            return False
        except json.JSONDecodeError:
            logging.error("Error decoding JSON from interface.json.")
            return False

    def check_token_validity(self) -> bool:
        """
        Check if the provided GitHub token is valid.
        """
        response = self.session.get(
            url=self.CHECK_TOKEN_VALIDITY_URL, headers=self.headers
        )
        if response.status_code == 200:
            logging.info("Token is valid.")
            return True
        elif response.status_code == 401:
            logging.error(
                f"Unauthorized: {response.status_code} - {response.json().get('message')}"
            )
        elif response.status_code == 403:
            logging.error(
                f"Forbidden: {response.status_code} - {response.json().get('message')}"
            )
        elif response.status_code == 404:
            logging.error(
                f"Not Found: {response.status_code} - {response.json().get('message')}"
            )
        else:
            logging.error(
                f"HTTP error occurred: {response.status_code} - {response.json().get('message')}"
            )
        return False

    def get_request_response(self, url: str, params: Optional[Dict] = None) -> Response:
        """
        Send a GET request and handle potential errors.
        """
        if params is None:
            params = {}
        try:
            response = self.session.get(url=url, headers=self.headers, params=params)
            response.raise_for_status()
        except HTTPError as http_err:
            status_code = http_err.response.status_code
            if status_code == 401:
                raise Exception(
                    f"Unauthorized: {status_code} - {http_err.response.json().get('message')}"
                )
            elif status_code == 403:
                raise Exception(
                    f"Forbidden: {status_code} - {http_err.response.json().get('message')}"
                )
            elif status_code == 404:
                raise Exception(
                    f"Not Found: {status_code} - {http_err.response.json().get('message')}"
                )
            else:
                raise Exception(
                    f"HTTP error occurred with status code: {http_err.response.status_code}"
                ) from http_err
        except RequestException as req_err:
            raise Exception(f"RequestException: {req_err}") from req_err
        return response

    def get_latest_version(self, per_page: int = 5) -> bool:
        """
        Get the latest version tag from the GitHub repository.
        """
        release_url = self.RELEASES_URL_TEMPLATE.format(repo=self.repo)
        for page in range(1, 101):
            params = {"per_page": per_page, "page": page}
            response = self.get_request_response(url=release_url, params=params)
            tags = response.json()
            # If there are no more tags, break the loop
            if not tags:
                break
            # Check if the tag is prerelease and if prerelease is needed
            for tag in tags:
                if tag["prerelease"] and not self.prerelease:
                    continue
                self.latest_version = tag["tag_name"]
                return True
        # Invalid tag
        return False

    def generate_changelog(self, per_page: int = 30) -> str:
        """
        Generate a changelog from the current version to the latest version.
        """
        release_url = self.RELEASES_URL_TEMPLATE.format(repo=self.repo)
        changelogs, start_flag = [], False
        for page in range(1, 101):
            params = {"per_page": per_page, "page": page}
            response = self.get_request_response(url=release_url, params=params)
            tags = response.json()
            if not tags:
                return f"Invaild tag! Please redownload in https://github.com/{self.repo}/releases/latest"
            for tag in tags:
                if tag["tag_name"] == self.current_version:
                    return "\n".join(changelogs)
                if not start_flag and tag["prerelease"] and not self.prerelease:
                    continue
                start_flag = True
                changelogs.append(f"# {tag['tag_name']}:\n\n{tag['body']}\n")
        return "\n".join(changelogs)

    def get_diff_content(self) -> str:
        """
        Get the diff content between two versions.
        """
        compare_url = self.COMPARE_URL_TEMPLATE.format(
            repo=self.repo,
            current_version=self.current_version,
            latest_version=self.latest_version,
        )
        try:
            response = self.get_request_response(url=compare_url)
            diff_url = response.json()["diff_url"]
            diff_response = self.get_request_response(url=diff_url)
            return diff_response.text
        except KeyError:
            raise Exception("Failed to retrieve the diff URL from the response.")

    def process_diff_content(self, diff_content: str) -> bool:
        """
        Process the diff content.
        """
        try:
            # assets/resource & assets/interface.json to resource & interface.json
            processed_content = diff_content.replace("assets/", "")
            self.diff_filename = f"{self.current_version}_{self.latest_version}.diff"
            with open(
                os.path.join(self.base_dir, self.diff_dir, self.diff_filename),
                "w",
                encoding="utf-8",
            ) as file:
                file.write(processed_content)
            return True
        except Exception as e:
            logging.error(f"An error occurred while processing the diff: {e}")
            return False

    def apply_patch(self) -> bool:
        """
        Apply the patch content to the local files.
        """
        try:
            original_cwd = os.getcwd()
            os.chdir(self.base_dir)

            patch_file_path = os.path.join(self.diff_dir, self.diff_filename)
            with open(
                patch_file_path,
                "r",
                encoding="utf-8",
            ) as patch_file:
                patch_content = patch_file.read()

            # 解析补丁
            patchset = PatchSet.from_string(patch_content)
            for patched_file in patchset:
                current_file_path = patched_file.path
                logging.info(f"Patching file {current_file_path}")

                # remove
                if patched_file.is_removed_file:
                    if os.path.exists(current_file_path):
                        os.remove(current_file_path)
                        logging.info(f"Removed file: {current_file_path}")
                    else:
                        logging.warning(
                            f"File {current_file_path} does not exist for removal, skipping..."
                        )
                    continue

                # rename
                if patched_file.is_rename:
                    if os.path.exists(current_file_path):
                        os.rename(current_file_path, patched_file.target_file)
                        logging.info(
                            f"Renamed file from {current_file_path} to {patched_file.target_file}"
                        )
                    else:
                        logging.warning(
                            f"File {current_file_path} does not exist for renaming, skipping..."
                        )
                        continue
                    current_file_path = patched_file.target_file

                if not os.path.exists(current_file_path):
                    # add
                    if patched_file.is_added_file:
                        with open(current_file_path, "w", encoding="utf-8") as new_file:
                            new_file.write("")
                        logging.info(f"Created new file: {current_file_path}")
                    else:
                        logging.warning(
                            f"File {current_file_path} does not exist, skipping..."
                        )
                        continue

                with open(current_file_path, "r", encoding="utf-8") as original_file:
                    original_content = original_file.readlines()

                # patch
                # 倒序处理所有 hunk，先处理删除行
                for hunk in reversed(list(patched_file)):
                    # 先处理删除行，根据 source_line_no 从后往前删除
                    for diff_line in reversed(hunk):
                        if diff_line.is_removed:
                            logging.debug(
                                f"Removing line at {diff_line.source_line_no}: {diff_line.value.strip()}"
                            )
                            if isinstance(diff_line.source_line_no, int):
                                original_content.pop(diff_line.source_line_no - 1)

                # 正序处理所有 hunk，根据 target_line_no 从前往后处理添加行
                for hunk in patched_file:
                    for diff_line in hunk:
                        if diff_line.is_added:
                            logging.debug(
                                f"Adding line at {diff_line.target_line_no}: {diff_line.value.strip()}"
                            )
                            if isinstance(diff_line.target_line_no, int):
                                original_content.insert(
                                    diff_line.target_line_no - 1, diff_line.value
                                )

                with open(current_file_path, "w", encoding="utf-8") as original_file:
                    original_file.writelines(original_content)

                logging.info(
                    f"Patched file saved as {current_file_path.encode('unicode_escape').decode('utf-8')}"
                )

            with open("interface.json", "r+", encoding="utf-8") as file:
                data = json.load(file)
                data["version"] = self.latest_version
                file.seek(0)  # Reset file pointer to the beginning
                json.dump(data, file, indent=4)
                file.truncate()  # Ensure the file is properly truncated
            os.chdir(original_cwd)
            return True
        except Exception as e:
            logging.error(f"An error occurred while applying the patch: {e}")
            return False
        finally:
            os.chdir(original_cwd)

    def patch(self) -> bool:
        """
        Get the diff content between two versions, process the diff, and then patch the local file.
        """
        try:
            diff_content = self.get_diff_content()
            if self.process_diff_content(diff_content):
                if self.apply_patch():
                    logging.info("Patch applied successfully.")
                    return True
                else:
                    logging.error("Failed to apply the patch.")
        except Exception as e:
            logging.error(f"An error occurred while patching: {e}")
        return False


if __name__ == "__main__":
    print("Step 1:")
    updater = MaaFrameworkUpdater(
        base_dir=".",
        token="your_github_token",
    )
    print("Step 2:")
    if updater.read_interface():
        print(f"Current version: {updater.current_version}")
        print("Step 3: Check")
        print(updater.check_token_validity())
        print("Step 4:")
        if updater.get_latest_version():
            print(f"Latest version: {updater.latest_version}")
            print("Step 5:")
            if updater.latest_version != updater.current_version:
                print(f"New version available: {updater.latest_version}")
                changelog = updater.generate_changelog()
                print(changelog)
                print("Step 6:")
                if updater.patch():
                    print("Patch applied successfully.")
                else:
                    print("Failed to apply patch.")
    print("Done!")
